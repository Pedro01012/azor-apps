"""O PC abre os jogos competitivos? Checagem de anti-cheat e do básico.

Veio do WinUtil (Get-WinUtilGameCompatReport), numa leitura só de PowerShell.
Cada item diz: status (ok / atencao / falha), quais jogos dependem dele, o que
fazer, e se o AZOR conserta sozinho (fix) ou se é na BIOS / no site do
fabricante.

Requisitos das páginas de suporte das publicadoras: Riot Vanguard (Valorant,
LoL), Activision RICOCHET (CoD), FACEIT (CS2), Epic (Fortnite) e o suporte do
Xbox para a rede (Teredo).
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

FIRMWARE_GAMES = "Valorant, League of Legends, CoD Warzone, CS2 na FACEIT e torneios do Fortnite"
ANTICHEAT_SERVICES = ("vgc", "EasyAntiCheat", "EasyAntiCheat_EOS", "BEService", "FACEIT")
XBOX_SERVICES = {"XblAuthManager": "Manual", "XblGameSave": "Manual", "XboxNetApiSvc": "Manual",
                 "GamingServices": "Automatic", "GamingServicesNet": "Automatic"}

_SCRIPT = r"""
$ErrorActionPreference='SilentlyContinue'
function RegV($p,$n){ try { (Get-ItemProperty -Path $p -Name $n -ErrorAction Stop).$n } catch { $null } }
$tpm=$null; $tpmErr=$null
try { $t=Get-CimInstance -Namespace 'root\cimv2\Security\MicrosoftTpm' -ClassName Win32_Tpm -ErrorAction Stop
      if($t){ $tpm=[pscustomobject]@{Spec=(([string]$t.SpecVersion -split ',')[0]).Trim();Enabled=[bool]$t.IsEnabled_InitialValue;Activated=[bool]$t.IsActivated_InitialValue} } } catch { $tpmErr=$_.Exception.Message }
$dg=$null; try { $dg=[int](Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard -ErrorAction Stop).VirtualizationBasedSecurityStatus } catch {}
$svc=@{}; foreach($n in @('vgc','EasyAntiCheat','EasyAntiCheat_EOS','BEService','FACEIT','XblAuthManager','XblGameSave','XboxNetApiSvc','GamingServices','GamingServicesNet')){ $s=Get-Service -Name $n -ErrorAction SilentlyContinue; if($s){ $svc[$n]=[string]$s.StartType } }
$gpus=@(Get-CimInstance Win32_VideoController | ForEach-Object { [pscustomobject]@{Name=[string]$_.Name;Pnp=[string]$_.PNPDeviceID;Version=[string]$_.DriverVersion;Date=$(if($_.DriverDate){$_.DriverDate.ToUniversalTime().ToString('yyyy-MM-dd')}else{$null})} })
[pscustomobject]@{
  SecureBoot=RegV 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' 'UEFISecureBootEnabled'
  Tpm=$tpm; TpmError=$tpmErr; Vbs=$dg
  Tcpip6=RegV 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' 'DisabledComponents'
  Services=$svc
  GameBar=[bool](Get-AppxPackage -Name 'Microsoft.XboxGamingOverlay')
  Mpo=RegV 'HKLM:\SOFTWARE\Microsoft\Windows\Dwm' 'OverlayTestMode'
  DvrPolicy=RegV 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\GameDVR' 'AllowGameDVR'
  History=RegV 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR' 'HistoricalCaptureEnabled'
  GameMode=RegV 'HKCU:\Software\Microsoft\GameBar' 'AutoGameModeEnabled'
  Gpus=$gpus
}
"""

GPU_VENDORS = {
    "10DE": ("NVIDIA", "https://www.nvidia.com/pt-br/drivers/"),
    "1002": ("AMD", "https://www.amd.com/pt/support/download/drivers.html"),
    "8086": ("Intel", "https://www.intel.com.br/content/www/br/pt/support/detect.html"),
}


def _check(id, name, status, games, detail, fix="", can_fix=False, link=""):
    return {"id": id, "name": name, "status": status, "games": games, "detail": detail,
            "fix": fix, "can_fix": can_fix, "link": link}


def report(core) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "checks": [], "detail": "Disponível somente no Windows."}
    try:
        d = core.powershell_json(_SCRIPT, timeout=90) or {}
    except Exception as exc:
        return {"ok": False, "checks": [], "detail": f"A leitura não terminou: {exc}"}
    checks: List[Dict[str, Any]] = []

    sb = d.get("SecureBoot")
    if sb is not None and int(sb) == 1:
        checks.append(_check("secure_boot", "Secure Boot", "ok", FIRMWARE_GAMES, "Ligado."))
    else:
        checks.append(_check("secure_boot", "Secure Boot", "falha", FIRMWARE_GAMES,
                             "Desligado." if sb is not None else "Não foi possível ler: o PC pode estar em modo legado (CSM).",
                             "Ligue o Secure Boot na BIOS (veja o passo a passo na tela BIOS)."))

    tpm = d.get("Tpm") or {}
    if d.get("TpmError"):
        checks.append(_check("tpm", "TPM 2.0", "atencao", FIRMWARE_GAMES,
                             "Leitura bloqueada sem administrador.", "Abra o AZOR como administrador para conferir."))
    elif tpm.get("Spec") == "2.0" and tpm.get("Enabled") and tpm.get("Activated"):
        checks.append(_check("tpm", "TPM 2.0", "ok", FIRMWARE_GAMES, "Presente e ligado."))
    else:
        checks.append(_check("tpm", "TPM 2.0", "falha", FIRMWARE_GAMES,
                             f"TPM {tpm.get('Spec')} (os jogos exigem 2.0)." if tpm.get("Spec") else "TPM desligado ou ausente.",
                             "Ligue o TPM na BIOS: Intel PTT ou AMD fTPM."))

    vbs = d.get("Vbs")
    if vbs == 2:
        checks.append(_check("vbs", "Segurança por virtualização (VBS)", "ok", "Vanguard e FACEIT", "Em execução."))
    else:
        checks.append(_check("vbs", "Segurança por virtualização (VBS)", "atencao", "Vanguard e FACEIT",
                             "Não está em execução. Só importa se o Valorant ou a FACEIT pedirem.",
                             "Ligue a virtualização (VT-x / SVM) na BIOS e a Integridade de Memória em Segurança do Windows."))

    dc = int(d.get("Tcpip6") or 0)
    if dc & 0x01:
        checks.append(_check("teredo", "Túnel Teredo (rede Xbox)", "atencao",
                             "CoD pelo Game Pass, chat de festa do Xbox",
                             "Os túneis IPv6 estão bloqueados.", "Religar o Teredo (precisa reiniciar).", True))
    else:
        checks.append(_check("teredo", "Túnel Teredo (rede Xbox)", "ok", "CoD pelo Game Pass, chat de festa do Xbox",
                             "Liberado."))

    services = d.get("Services") or {}
    off_ac = [n for n in ANTICHEAT_SERVICES if str(services.get(n) or "") == "Disabled"]
    checks.append(_check("anticheat", "Serviços de anti-cheat",
                         "falha" if off_ac else "ok",
                         "Valorant/LoL (vgc), Fortnite (EasyAntiCheat), BattlEye, FACEIT",
                         ("Desligados por outro otimizador: " + ", ".join(off_ac) + ".") if off_ac
                         else "Nenhum anti-cheat instalado está desligado.",
                         "Voltar para Manual, que é como os anti-cheats iniciam." if off_ac else "", bool(off_ac)))

    off_xbox = [n for n in XBOX_SERVICES if str(services.get(n) or "") == "Disabled"]
    checks.append(_check("xbox", "Serviços do Xbox", "atencao" if off_xbox else "ok",
                         "Game Pass, login com conta Microsoft em jogos, saves na nuvem",
                         ("Desligados: " + ", ".join(off_xbox) + ".") if off_xbox else "Nenhum serviço do Xbox desligado.",
                         "Voltar ao padrão do Windows." if off_xbox else "", bool(off_xbox)))

    if d.get("GameBar"):
        checks.append(_check("gamebar", "Xbox Game Bar", "ok", "Fortnite e jogos que chamam o overlay", "Instalada."))
    else:
        checks.append(_check("gamebar", "Xbox Game Bar", "atencao", "Fortnite e jogos que chamam o overlay",
                             "Removida por outro otimizador: alguns jogos mostram o erro 'ms-gamingoverlay'.",
                             "Reinstalar pela Microsoft Store.", True,
                             "ms-windows-store://pdp/?productid=9NZKPSTSNW4P"))

    mpo = d.get("Mpo")
    if mpo is not None and int(mpo) == 5:
        checks.append(_check("mpo", "Multiplane Overlay (MPO)", "atencao", "Jogos em tela cheia",
                             "Desligado. Já travou a imagem do Fortnite e de outros jogos.",
                             "Voltar ao padrão do Windows (precisa reiniciar).", True))
    else:
        checks.append(_check("mpo", "Multiplane Overlay (MPO)", "ok", "Jogos em tela cheia", "No padrão do Windows."))

    display = core.display_refresh_state()
    if display.get("below_max"):
        checks.append(_check("refresh", "Taxa do monitor", "atencao", "Todos os jogos",
                             f"Monitor em {display.get('current_hz')} Hz, mas aceita {display.get('max_hz')} Hz. "
                             f"O jogo nunca vai mostrar mais que {display.get('current_hz')} FPS.",
                             f"Colocar em {display.get('max_hz')} Hz agora.", True))
    elif display.get("ok"):
        checks.append(_check("refresh", "Taxa do monitor", "ok", "Todos os jogos",
                             f"{display.get('current_hz')} Hz - a máxima deste monitor."))

    gpus = d.get("Gpus") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    driver_lines, worst, links = [], "ok", []
    for g in gpus:
        vendor = re.search(r"VEN_([0-9A-Fa-f]{4})", str(g.get("Pnp") or ""))
        vendor = vendor.group(1).upper() if vendor else ""
        if vendor not in GPU_VENDORS:
            continue
        label, url = GPU_VENDORS[vendor]
        name = str(g.get("Name") or label)
        if "basic display" in name.lower() or "vídeo básico" in name.lower():
            driver_lines.append(f"A placa {label} está SEM driver.")
            worst = "falha"
            links.append(url)
            continue
        date = g.get("Date")
        months = None
        if date:
            try:
                months = int((time.time() - time.mktime(time.strptime(date, "%Y-%m-%d"))) / (30 * 86400))
            except Exception:
                months = None
        driver_lines.append(f"{name}: driver de {date or '?'}" + (f" ({months} meses)" if months is not None else ""))
        if months is not None and months >= 6 and worst != "falha":
            worst = "atencao"
            links.append(url)
    if driver_lines:
        checks.append(_check("gpu_driver", "Driver da placa de vídeo", worst, "Todos os jogos",
                             "; ".join(driver_lines) + ".",
                             "Baixar o driver mais recente no site do fabricante." if worst != "ok" else "",
                             worst != "ok", links[0] if links else ""))

    dvr_policy = d.get("DvrPolicy")
    if (dvr_policy is None or int(dvr_policy) != 0) and int(d.get("History") or 0) == 1:
        checks.append(_check("recording", "Gravação em segundo plano", "atencao", "Todos os jogos",
                             "A Game Bar grava a partida o tempo todo. Custa FPS.", "Desligar.", True))
    else:
        checks.append(_check("recording", "Gravação em segundo plano", "ok", "Todos os jogos", "Desligada."))

    gm = d.get("GameMode")
    if gm is not None and int(gm) == 0:
        checks.append(_check("game_mode", "Modo de Jogo", "atencao", "Todos os jogos", "Desligado.", "Ligar.", True))
    else:
        checks.append(_check("game_mode", "Modo de Jogo", "ok", "Todos os jogos", "Ligado."))

    from . import cleanup as _cleanup
    disk = _cleanup.disk_usage()
    if disk and disk.get("used_pct", 0) >= 90:
        checks.append(_check("disk", "Espaço no disco do Windows", "atencao", "Atualizações do Windows e dos jogos",
                             f"{disk.get('free_gb')} GB livres de {disk.get('total_gb')} GB.",
                             "Rodar a Limpeza do AZOR.", True))
    elif disk:
        checks.append(_check("disk", "Espaço no disco do Windows", "ok", "Atualizações do Windows e dos jogos",
                             f"{disk.get('free_gb')} GB livres."))

    order = {"falha": 0, "atencao": 1, "ok": 2}
    checks.sort(key=lambda c: order[c["status"]])
    return {"ok": True, "checks": checks,
            "problems": sum(1 for c in checks if c["status"] != "ok"),
            "fixable": sum(1 for c in checks if c["status"] != "ok" and c["can_fix"])}


def fix(core, check_id: str, progress: Optional[Callable] = None) -> Dict[str, Any]:
    """Conserta um item do relatório. Só o que dá para resolver pelo Windows."""
    if check_id == "teredo":
        cur = core.reg_read("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents")
        value = int(cur.get("value") or 0) & ~0x01
        core.reg_write("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents", value)
        core.run_hidden(["netsh", "interface", "teredo", "set", "state", "type=default"], timeout=30)
        ok = not (int(core.reg_read("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters",
                                    "DisabledComponents").get("value") or 0) & 0x01)
        return {"ok": ok, "restart": True, "detail": "Teredo liberado. Reinicie o PC." if ok else "Não confirmado."}
    if check_id == "anticheat":
        done = []
        for name in ANTICHEAT_SERVICES:
            if core.service_state(name).get("disabled"):
                ok, _ = core.set_service_start_verified(name, "Manual")
                if ok:
                    done.append(name)
        return {"ok": True, "detail": ("Voltaram para Manual: " + ", ".join(done)) if done else "Nada a consertar."}
    if check_id == "xbox":
        done = []
        for name, start in XBOX_SERVICES.items():
            if core.service_state(name).get("disabled"):
                ok, _ = core.set_service_start_verified(name, start)
                if ok:
                    done.append(name)
        return {"ok": True, "detail": ("Voltaram ao padrão: " + ", ".join(done)) if done else "Nada a consertar."}
    if check_id == "mpo":
        core.reg_delete_value("HKLM", r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode")
        ok = not core.reg_read("HKLM", r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode").get("exists")
        return {"ok": ok, "restart": True, "detail": "MPO de volta ao padrão. Reinicie o PC." if ok else "Não confirmado."}
    if check_id == "refresh":
        state = core.display_refresh_state()
        ok, detail = core.set_display_refresh_verified(int(state.get("max_hz") or 0))
        return {"ok": ok, "detail": detail}
    if check_id in ("recording", "game_mode"):
        from . import engine
        task = "game_dvr" if check_id == "recording" else "game_mode"
        return engine.apply_task(task, "maximo")
    return {"ok": False, "detail": "Este item se resolve fora do Windows (BIOS ou site do fabricante)."}
