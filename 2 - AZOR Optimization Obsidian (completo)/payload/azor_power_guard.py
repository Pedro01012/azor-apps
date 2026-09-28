# -*- coding: utf-8 -*-
"""Por que o plano de energia volta sozinho, e as camadas que seguram ele.

Em notebook, trocar o plano de energia e a parte facil. O plano *continuar* trocado
depois do logon, depois de tirar da tomada e depois do proximo boot e o problema
real, e ele quase nunca e culpa do Windows sozinho:

  1. software do fabricante (Lenovo Vantage, MyASUS/Armoury Crate, Dell Power
     Manager, HP Command Center, Alienware/Acer/MSI Center) reaplica o esquema
     dele no logon e a cada troca AC<->bateria. Causa numero 1;
  2. Modern Standby (S0ix): quem manda de verdade e o *overlay* de Power Mode,
     nao o esquema. Trocar so o esquema nao muda quase nada;
  3. Fast Startup: o "desligar" e uma hibernacao parcial que restaura estado antigo;
  4. politica de grupo/Intune definindo o esquema ativo;
  5. o esquema duplicado foi apagado por alguma limpeza e o Windows caiu no
     Equilibrado.

Este modulo primeiro DIAGNOSTICA qual desses casos e o do PC do usuario, e so
depois aplica camadas, da mais leve para a mais forte. Nenhuma camada e aplicada
sozinha: cada uma e um clique, com o que ela custa escrito antes.
"""
from __future__ import annotations

import json
import os
import re
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

import azor_core as core

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
POLICY_KEY = r"SOFTWARE\Policies\Microsoft\Power\PowerSettings"
POLICY_NAME = "ActivePowerScheme"
FAST_STARTUP_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"
FAST_STARTUP_NAME = "HiberbootEnabled"
OVERLAY_KEY = r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes"
OVERLAY_AC_NAME = "ActiveOverlayAcPowerScheme"
OVERLAY_DC_NAME = "ActiveOverlayDcPowerScheme"
GUARD_TASK = "AzorPowerGuard"

# GUIDs de overlay (Power Mode) publicados pela Microsoft. Um GUID fora desta
# tabela nao e adivinhado: e mostrado como desconhecido, com o valor cru.
OVERLAY_GUIDS = {
    "00000000-0000-0000-0000-000000000000": "Equilibrado / recomendado pelo Windows",
    "ded574b5-45a0-4f42-8737-46345c09c238": "Melhor desempenho",
    "961cc777-2547-4f9d-8174-7d86181b8a7a": "Melhor eficiencia de energia",
    "3af9b8d9-7c97-431d-ad78-34a8bfea439f": "Desempenho maximo (equipamento)",
}
OVERLAY_ALIASES = {
    "max": "overlay_scheme_max",
    "performance": "overlay_scheme_max",
    "balanced": "scheme_current",
    "min": "overlay_scheme_min",
    "efficiency": "overlay_scheme_min",
}

# Fragmentos de nome de processo/servico de software de energia de fabricante.
# O AZOR nunca desinstala nem desativa nada disso sozinho: ele so identifica
# quem esta competindo pelo controle e diz ao usuario o que fazer.
OEM_SIGNATURES = [
    ("Lenovo Vantage / Lenovo Energy", ("lenovovantage", "vantage.service", "imcontroller", "lenovo.modern", "energymanagement")),
    ("Dell Power Manager", ("dellpowermanager", "dell.powermanager", "dpmservice", "dellcommandpower")),
    ("ASUS Armoury Crate / MyASUS", ("armourycrate", "armoury", "asussystemanalysis", "asusoptimization", "myasus", "atkexcomsvc")),
    ("HP Command Center / HP Power Manager", ("hpcommandcenter", "hppowermanager", "hpsystemevent", "hpomencommand")),
    ("MSI Center / Dragon Center", ("msicenter", "dragoncenter", "msi_center", "mystericlightservice")),
    ("Alienware Command Center", ("awcc", "alienware", "aweservice")),
    ("Acer PredatorSense / NitroSense", ("predatorsense", "nitrosense", "acerpower")),
    ("Razer Synapse", ("razersynapse", "razer central")),
    ("Gigabyte Control Center", ("gigabytecontrol", "gcc.service", "aorusservice")),
]


def _machine_identity() -> Dict[str, Any]:
    """Fabricante e modelo. Importa porque a causa nº1 e o software do fabricante."""
    def read() -> Dict[str, Any]:
        try:
            # powershell_json ja serializa: um ConvertTo-Json aqui devolveria
            # uma string de JSON dentro de JSON, e o dicionario vinha vazio.
            data = core.powershell_json(
                "Get-CimInstance Win32_ComputerSystem | "
                "Select-Object -First 1 Manufacturer,Model,SystemFamily",
                timeout=25) or {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {"manufacturer": data.get("Manufacturer"), "model": data.get("Model"),
                "family": data.get("SystemFamily")}
    return core.cached_reading("power_machine_identity", 900.0, read)


def _reg_read_dword(root: str, path: str, name: str) -> Optional[int]:
    value = core.reg_read(root, path, name)
    if not value.get("exists"):
        return None
    try:
        return int(value.get("value"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Passo 1 - diagnostico
# ---------------------------------------------------------------------------
def _sleep_states() -> Dict[str, Any]:
    """`powercfg /a` diz se este PC usa Modern Standby, e isso muda a estrategia."""
    if os.name != "nt":
        return {"supported": False}
    try:
        p = core.run_hidden(["powercfg", "/a"], timeout=10)
        text = ((p.stdout or "") + "\n" + (p.stderr or ""))
    except Exception as exc:
        return {"supported": False, "error": str(exc)}
    # `powercfg /a` imprime DOIS blocos: os estados disponiveis e os NAO
    # disponiveis. Procurar "S0" no texto inteiro marcava Modern Standby em
    # desktop justamente porque o S0 aparece na lista do que nao existe.
    # Os cabecalhos sao as unicas linhas terminadas em ":", em qualquer idioma.
    lines = text.splitlines()
    headers = [i for i, ln in enumerate(lines) if ln.strip().endswith(":")]
    if headers:
        end = headers[1] if len(headers) > 1 else len(lines)
        available = chr(10).join(lines[headers[0] + 1:end])
    else:
        available = ""
    low = available.lower()
    return {
        "supported": True,
        "modern_standby": "s0" in low,
        "s3_available": "s3" in low,
        "hibernate_available": ("hibern" in low),
        "available": [ln.strip() for ln in available.splitlines() if ln.strip()],
        "raw": text.strip()[:1500],
    }


def _overlay_state() -> Dict[str, Any]:
    ac = core.reg_read("HKLM", OVERLAY_KEY, OVERLAY_AC_NAME)
    dc = core.reg_read("HKLM", OVERLAY_KEY, OVERLAY_DC_NAME)

    def describe(entry: Dict[str, Any]) -> Dict[str, Any]:
        if not entry.get("exists"):
            return {"guid": None, "label": "Não exposto neste Windows"}
        guid = str(entry.get("value") or "").strip("{} ").lower()
        return {"guid": guid, "label": OVERLAY_GUIDS.get(guid, f"Overlay não reconhecido ({guid})")}

    return {"ac": describe(ac), "dc": describe(dc),
            "supported": bool(ac.get("exists") or dc.get("exists"))}


def _oem_power_software() -> List[Dict[str, str]]:
    """Quem mais esta mexendo em energia neste PC agora."""
    found: List[Dict[str, str]] = []
    try:
        names = [str(n).lower() for n in core._process_names()]
    except Exception:
        names = []
    joined = " ".join(names)
    for label, fragments in OEM_SIGNATURES:
        hit = next((f for f in fragments if f in joined), None)
        if hit:
            found.append({"name": label, "evidence": f"processo contendo '{hit}' em execução"})
    return found


def diagnose(force: bool = False) -> Dict[str, Any]:
    """Fotografia completa de quem controla a energia deste PC."""
    if os.name != "nt":
        return {"ok": False, "supported": False, "reason": "Windows only"}

    schemes = core.list_power_schemes()
    active = (core.get_active_power_scheme() or "").lower()
    azor = next((s for s in schemes if str(s.get("name") or "").strip().casefold()
                 == core.AZOR_POWER_NAME.casefold()), None)
    policy = core.reg_read("HKLM", POLICY_KEY, POLICY_NAME)
    hiberboot = _reg_read_dword("HKLM", FAST_STARTUP_KEY, FAST_STARTUP_NAME)
    profile = core.hardware_profile(force=force)
    oem = _oem_power_software()
    sleep = _sleep_states()
    overlay = _overlay_state()
    task = guard_task_status()

    causes: List[Dict[str, str]] = []

    def cause(severity: str, title: str, detail: str, layer: str = "") -> None:
        causes.append({"severity": severity, "title": title, "detail": detail, "layer": layer})

    if oem:
        cause("high", "Software de energia do fabricante em execução",
              "Encontrado: " + "; ".join(x["name"] for x in oem) + ". "
              "Esse tipo de software reaplica o próprio perfil no logon e a cada troca de "
              "tomada/bateria — é a causa nº 1 de plano que volta sozinho em notebook. "
              "O AZOR não desinstala nem desativa nada disso: configure o perfil equivalente "
              "dentro dele, ou use a camada de reforço abaixo.", "E")
    if sleep.get("modern_standby"):
        cause("high", "Modern Standby (S0 Low Power Idle) ativo",
              "Neste tipo de notebook quem manda de verdade é o Power Mode (overlay), não o "
              "esquema de energia. Trocar só o esquema muda pouco: o AZOR precisa fixar os dois.", "D")
    if hiberboot == 1:
        cause("medium", "Inicialização Rápida ligada",
              "O 'desligar' do Windows vira uma hibernação parcial e pode restaurar o estado "
              "anterior, inclusive o esquema de energia. Desligar a Inicialização Rápida faz o "
              "boot demorar alguns segundos a mais e resolve essa classe de reversão.", "B")
    if policy.get("exists"):
        locked = str(policy.get("value") or "").strip("{} ").lower()
        if azor and locked == str(azor.get("guid") or "").lower():
            cause("good", "Política já trava o plano do AZOR",
                  f"HKLM\\{POLICY_KEY}\\{POLICY_NAME} = {locked}. Essa é a mesma chave da GPO "
                  "'Selecionar um plano de energia ativo' e sobrevive a reinício.", "A")
        else:
            cause("high", "Uma política define outro plano ativo",
                  f"HKLM\\{POLICY_KEY}\\{POLICY_NAME} = {locked}. Enquanto essa política existir, "
                  "ela ganha da sua escolha. Pode ser do domínio/Intune da empresa — nesse caso "
                  "a decisão é do administrador, não do AZOR.", "A")
    if not azor:
        cause("medium", "O plano AZOR ainda não existe neste PC",
              "Sem o plano próprio, não há o que proteger. Crie o AZOR FPS BOOST antes de "
              "aplicar as camadas.", "")
    elif active != str(azor.get("guid") or "").lower():
        cause("high", "O plano AZOR existe mas não está ativo",
              f"Ativo agora: {active or 'desconhecido'}.", "")
    else:
        cause("good", "O plano AZOR está ativo agora", f"GUID {active}.", "")

    order = {"high": 0, "medium": 1, "good": 2}
    causes.sort(key=lambda c: order.get(c["severity"], 3))

    return {
        "ok": True, "supported": True, "time": core._ts(),
        "schemes": schemes,
        "active_guid": active or None,
        "azor_scheme": azor,
        "azor_active": bool(azor and active == str(azor.get("guid") or "").lower()),
        "policy_lock": {"exists": bool(policy.get("exists")),
                        "value": str(policy.get("value") or "").strip("{} ").lower() or None},
        "fast_startup": hiberboot,
        "overlay": overlay,
        "sleep": sleep,
        "oem_software": oem,
        "battery": bool(profile.get("battery")),
        "machine": _machine_identity(),
        "guard_task": task,
        "watchdog": watchdog_status(),
        "causes": causes,
        "layers": layers_state(),
    }


# ---------------------------------------------------------------------------
# Camada A - travar por politica
# ---------------------------------------------------------------------------
def set_policy_lock(enabled: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Windows only"
    if not core.is_admin():
        return False, "Travar o plano por política escreve em HKLM e exige o AZOR como administrador."
    if not enabled:
        try:
            core.reg_delete_value("HKLM", POLICY_KEY, POLICY_NAME)
        except Exception as exc:
            return False, f"Não foi possível remover a política: {exc}"
        gone = not core.reg_read("HKLM", POLICY_KEY, POLICY_NAME).get("exists")
        core.journal("power_policy_lock", enabled=False, ok=gone)
        return gone, ("Trava por política removida e confirmada." if gone
                      else "A remoção da política não pôde ser confirmada.")
    ok, guid, detail = core.ensure_azor_fps_boost_scheme()
    if not ok or not guid:
        return False, detail
    try:
        core.reg_write("HKLM", POLICY_KEY, POLICY_NAME, guid)
    except Exception as exc:
        return False, f"Não foi possível gravar a política: {exc}"
    check = core.reg_read("HKLM", POLICY_KEY, POLICY_NAME)
    ok = bool(check.get("exists")) and str(check.get("value") or "").strip("{} ").lower() == guid.lower()
    core.journal("power_policy_lock", enabled=True, guid=guid, ok=ok)
    return ok, (f"Plano travado por política e relido ({guid}). Equivale à GPO 'Selecionar um plano "
                "de energia ativo' e sobrevive a reinício." if ok
                else "A política foi gravada mas não foi confirmada na releitura.")


def policy_lock_state() -> Dict[str, Any]:
    entry = core.reg_read("HKLM", POLICY_KEY, POLICY_NAME)
    return {"exists": bool(entry.get("exists")),
            "value": str(entry.get("value") or "").strip("{} ").lower() or None}


# ---------------------------------------------------------------------------
# Camada B - Fast Startup
# ---------------------------------------------------------------------------
def set_fast_startup(enabled: bool) -> Tuple[bool, str]:
    """Liga/desliga a Inicializacao Rapida mantendo a hibernacao intacta.

    Usa a chave HiberbootEnabled em vez de `powercfg /h off` justamente para nao
    apagar o arquivo de hibernacao de quem usa hibernar.
    """
    if os.name != "nt":
        return False, "Windows only"
    if not core.is_admin():
        return False, "Alterar a Inicialização Rápida escreve em HKLM e exige administrador."
    core.capture_restore_point()
    try:
        core.reg_write("HKLM", FAST_STARTUP_KEY, FAST_STARTUP_NAME, 1 if enabled else 0)
    except Exception as exc:
        return False, f"Não foi possível gravar HiberbootEnabled: {exc}"
    now = _reg_read_dword("HKLM", FAST_STARTUP_KEY, FAST_STARTUP_NAME)
    ok = now == (1 if enabled else 0)
    core.journal("fast_startup", enabled=bool(enabled), observed=now, ok=ok)
    if not ok:
        return False, f"O valor foi gravado mas a releitura retornou {now}."
    return True, ("Inicialização Rápida ligada e confirmada." if enabled else
                  "Inicialização Rápida desligada e confirmada. O boot fica alguns segundos mais "
                  "lento e o desligamento passa a ser um desligamento de verdade. A hibernação "
                  "continua disponível.")


# ---------------------------------------------------------------------------
# Camada C - tarefa agendada de reforco (opt-in explicito)
# ---------------------------------------------------------------------------
_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>AZOR Power Guard: reaplica o plano de energia escolhido pelo usuario apos o logon, apos o boot e quando a fonte de energia muda. Executa apenas powercfg.exe do Windows.</Description>
    <URI>\\{name}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><Delay>PT10S</Delay></LogonTrigger>
    <BootTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></BootTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Delay>PT5S</Delay>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=105)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>%SystemRoot%\\System32\\powercfg.exe</Command>
      <Arguments>/setactive {guid}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def guard_task_status() -> Dict[str, Any]:
    if os.name != "nt":
        return {"supported": False, "configured": False}
    try:
        q = core.run_hidden(["schtasks", "/Query", "/TN", GUARD_TASK, "/FO", "LIST"], timeout=10)
        text = (q.stdout or "") + (q.stderr or "")
        return {"supported": True, "configured": q.returncode == 0, "detail": text.strip()[:600]}
    except Exception as exc:
        return {"supported": True, "configured": False, "detail": str(exc)}


def set_guard_task(enabled: bool = True) -> Tuple[bool, str]:
    """Cria/remove a tarefa de reforco. NUNCA e criada automaticamente.

    A tarefa nao roda nada do AZOR: a acao dela e o proprio powercfg.exe do
    Windows. Isso importa porque a build limpa nao cria persistencia de si mesma,
    e porque uma tarefa que so chama um binario do sistema e auditavel por
    qualquer um pelo Agendador de Tarefas.
    """
    if os.name != "nt":
        return False, "Windows only"
    if not core.is_admin():
        return False, "Criar ou remover a tarefa de reforço exige o AZOR como administrador."
    if not enabled:
        try:
            core.run_hidden(["schtasks", "/Delete", "/TN", GUARD_TASK, "/F"], timeout=12)
        except Exception as exc:
            return False, f"Não foi possível remover a tarefa: {exc}"
        gone = not guard_task_status().get("configured")
        core.journal("power_guard_task", enabled=False, ok=gone)
        return gone, ("Tarefa de reforço removida e confirmada." if gone
                      else "A remoção da tarefa não pôde ser confirmada.")
    ok, guid, detail = core.ensure_azor_fps_boost_scheme()
    if not ok or not guid:
        return False, detail
    xml_path = core.DATA_DIR / "azor_power_guard.xml"
    try:
        xml_path.write_text(_TASK_XML.format(name=GUARD_TASK, guid=guid), encoding="utf-16")
        p = core.run_hidden(["schtasks", "/Create", "/TN", GUARD_TASK, "/XML", str(xml_path), "/F"], timeout=20)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "O Agendador recusou a tarefa.").strip()
    except Exception as exc:
        return False, f"Falha ao criar a tarefa: {exc}"
    finally:
        try:
            xml_path.unlink()
        except Exception:
            pass
    configured = guard_task_status().get("configured")
    core.journal("power_guard_task", enabled=True, guid=guid, ok=bool(configured))
    return bool(configured), ("Tarefa de reforço criada e confirmada no Agendador. Ela roda "
                              "powercfg.exe do Windows no logon, 30 s após o boot e quando a fonte "
                              "de energia muda — sempre depois do software do fabricante."
                              if configured else "A tarefa foi criada mas não foi confirmada na consulta.")


# ---------------------------------------------------------------------------
# Camada D - overlay (Power Mode)
# ---------------------------------------------------------------------------
def set_overlay(mode: str = "max") -> Tuple[bool, str]:
    """Em Modern Standby, e o overlay que manda. Fixar so o esquema nao basta."""
    if os.name != "nt":
        return False, "Windows only"
    alias = OVERLAY_ALIASES.get(str(mode).lower())
    if not alias:
        return False, f"Modo de overlay desconhecido: {mode}."
    before = _overlay_state()
    p = core.run_hidden(["powercfg", "/overlaysetactive", alias], timeout=10)
    if p.returncode != 0:
        return False, (p.stderr or p.stdout or "powercfg recusou o overlay.").strip()
    time.sleep(0.2)
    after = _overlay_state()
    if not after.get("supported"):
        return False, ("O comando foi aceito, mas este Windows não expõe o overlay ativo no "
                       "registro, então o AZOR não consegue confirmar. Nada é reportado como "
                       "verificado sem releitura.")
    changed = after["ac"]["guid"] != before["ac"]["guid"] or before["ac"]["guid"] is None
    core.journal("power_overlay", mode=mode, before=before["ac"]["guid"], after=after["ac"]["guid"])
    label = after["ac"]["label"]
    return True, (f"Power Mode relido como: {label}." if changed or after["ac"]["guid"]
                  else f"Overlay aplicado; leitura atual: {label}.")


def overlay_state() -> Dict[str, Any]:
    return _overlay_state()


# ---------------------------------------------------------------------------
# Camada F - watchdog em sessao
# ---------------------------------------------------------------------------
class _PowerWatchdog:
    """Observa o esquema ativo enquanto o AZOR esta aberto e reaplica em segundos.

    Isto NAO e um servico: ele morre junto com o app, de proposito. A persistencia
    fora da sessao e a camada C, que o usuario liga explicitamente.
    """

    def __init__(self) -> None:
        self.active = False
        self.reverts = 0
        self.last_revert: Optional[str] = None
        self.last_seen: Optional[str] = None
        self.started_at: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _loop(self) -> None:
        target = ""
        while not self._stop.wait(2.0):
            try:
                if not target:
                    found = core._scheme_by_profile("azor_fps_boost")
                    target = str(found.get("guid") or "").lower() if found else ""
                    if not target:
                        continue
                active = (core.get_active_power_scheme() or "").lower()
                self.last_seen = active or None
                if active and active != target:
                    ok, _ = core.set_power_profile("azor_fps_boost")
                    if ok:
                        self.reverts += 1
                        self.last_revert = core._ts()
                        core.journal("power_watchdog_revert", found=active, restored=target)
                        core.log(f"Power watchdog: plano trocado para {active}, AZOR reaplicado.")
            except Exception as exc:
                core.log(f"Power watchdog: {exc}")

    def start(self) -> Tuple[bool, str]:
        if os.name != "nt":
            return False, "Windows only"
        if self.active and self._thread and self._thread.is_alive():
            return True, "O guardião do plano de energia já está ativo nesta sessão."
        self._stop.clear()
        self.active = True
        self.started_at = core._ts()
        self._thread = threading.Thread(target=self._loop, name="AzorPowerWatchdog", daemon=True)
        self._thread.start()
        core.journal("power_watchdog", active=True)
        return True, ("Guardião do plano ativo. Enquanto o AZOR estiver aberto, qualquer troca de "
                      "plano é revertida em até 2 segundos — e aparece contada aqui.")

    def stop(self) -> Tuple[bool, str]:
        self.active = False
        self._stop.set()
        core.journal("power_watchdog", active=False, reverts=self.reverts)
        return True, "Guardião do plano de energia desativado."

    def status(self) -> Dict[str, Any]:
        running = bool(self.active and self._thread and self._thread.is_alive())
        return {"active": running, "reverts": self.reverts, "last_revert": self.last_revert,
                "last_seen": self.last_seen, "started_at": self.started_at}


WATCHDOG = _PowerWatchdog()


def watchdog_status() -> Dict[str, Any]:
    return WATCHDOG.status()


# ---------------------------------------------------------------------------
# Passo 3 - teste de persistencia atraves do reboot
# ---------------------------------------------------------------------------
def _test_file():
    return core.DATA_DIR / "power_persistence_test.json"


def persistence_test_arm() -> Dict[str, Any]:
    """Grava o que deveria continuar valendo depois do reinicio."""
    found = core._scheme_by_profile("azor_fps_boost")
    guid = str(found.get("guid") or "").lower() if found else ""
    if not guid:
        return {"ok": False, "detail": "O plano AZOR ainda não existe; nada a testar."}
    state = {
        "armed_at": core._ts(),
        "expected_guid": guid,
        "active_at_arm": (core.get_active_power_scheme() or "").lower(),
        "overlay_at_arm": _overlay_state()["ac"]["guid"],
        "boot_id": _boot_id(),
        "runs": [],
    }
    core._safe_json_write(_test_file(), state)
    core.journal("power_persistence_test", phase="arm", guid=guid)
    return {"ok": True, "detail": ("Teste armado. Reinicie o PC quando quiser; ao abrir o AZOR "
                                   "de novo, ele confere sozinho se o plano se manteve."),
            "state": state}


def _boot_id() -> Optional[float]:
    """Identidade grosseira do boot atual: hora de inicializacao do sistema."""
    try:
        raw = core.powershell("(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToFileTimeUtc()", timeout=20)
        return float(str(raw).strip())
    except Exception:
        return None


def persistence_test_check() -> Dict[str, Any]:
    state = core._safe_json_read(_test_file(), {})
    if not isinstance(state, dict) or not state.get("expected_guid"):
        return {"ok": True, "armed": False, "detail": "Nenhum teste de persistência armado."}
    active = (core.get_active_power_scheme() or "").lower()
    boot = _boot_id()
    rebooted = bool(state.get("boot_id") and boot and boot != state.get("boot_id"))
    held = active == str(state.get("expected_guid")).lower()
    runs = list(state.get("runs") or [])
    if rebooted:
        runs.append({"at": core._ts(), "active": active, "held": held})
        state["runs"] = runs
        state["boot_id"] = boot
        core._safe_json_write(_test_file(), state)
        core.journal("power_persistence_test", phase="check", held=held, active=active,
                     reboots=len(runs))
    survived = sum(1 for r in runs if r.get("held"))
    return {
        "ok": True, "armed": True, "held_now": held, "active_guid": active or None,
        "expected_guid": state.get("expected_guid"), "reboots_observed": len(runs),
        "reboots_survived": survived, "runs": runs[-5:],
        "detail": (f"{survived} de {len(runs)} reinício(s) observado(s) mantiveram o plano."
                   if runs else "Teste armado; ainda não houve um reinício desde então."),
    }


def persistence_test_clear() -> Dict[str, Any]:
    try:
        _test_file().unlink()
    except Exception:
        pass
    return {"ok": True, "detail": "Teste de persistência encerrado."}


# ---------------------------------------------------------------------------
# Estado consolidado das camadas
# ---------------------------------------------------------------------------
def layers_state() -> List[Dict[str, Any]]:
    policy = policy_lock_state()
    hiberboot = _reg_read_dword("HKLM", FAST_STARTUP_KEY, FAST_STARTUP_NAME)
    overlay = _overlay_state()
    task = guard_task_status()
    wd = watchdog_status()
    azor = core._scheme_by_profile("azor_fps_boost")
    azor_guid = str(azor.get("guid") or "").lower() if azor else ""
    return [
        {"id": "A", "name": "Travar por política",
         "state": "on" if (policy["exists"] and policy["value"] == azor_guid) else
                  ("conflict" if policy["exists"] else "off"),
         "detail": ("A mesma chave da GPO 'Selecionar um plano de energia ativo'. Sobrevive a "
                    "reinício e bloqueia a maior parte das trocas."),
         "cost": "Enquanto estiver ligada, trocar de plano pelo Painel de Controle não adianta — "
                 "nem para você. Desligue esta camada antes de mudar de plano.",
         "action_on": "power_policy_lock_on", "action_off": "power_policy_lock_off",
         "requires_admin": True},
        {"id": "B", "name": "Desligar Inicialização Rápida",
         "state": "on" if hiberboot == 0 else ("off" if hiberboot == 1 else "unknown"),
         "detail": "Impede que o 'desligar' restaure um estado antigo junto com o plano anterior.",
         "cost": "O boot fica alguns segundos mais lento. A hibernação continua funcionando.",
         "action_on": "fast_startup_off", "action_off": "fast_startup_on",
         "requires_admin": True},
        {"id": "C", "name": "Tarefa de reforço",
         "state": "on" if task.get("configured") else "off",
         "detail": ("Roda powercfg.exe do Windows no logon, 30 s depois do boot e quando a fonte "
                    "muda — de propósito depois do software do fabricante."),
         "cost": "É a única coisa que o AZOR deixa registrada no Windows. Ela não executa nada do "
                 "AZOR, só powercfg, e sai limpa quando você desliga esta camada.",
         "action_on": "power_guard_task_on", "action_off": "power_guard_task_off",
         "requires_admin": True},
        {"id": "D", "name": "Fixar o Power Mode (overlay)",
         "state": "on" if overlay["ac"]["guid"] == "ded574b5-45a0-4f42-8737-46345c09c238" else
                  ("unknown" if not overlay.get("supported") else "off"),
         "detail": ("Em notebook com Modern Standby é o overlay que manda; o esquema é só a base. "
                    f"Agora: {overlay['ac']['label']}."),
         "cost": "Melhor desempenho consome mais bateria. Em notebook, use junto com a leitura de "
                 "temperatura antes de deixar fixo.",
         "action_on": "power_overlay_max", "action_off": "power_overlay_balanced",
         "requires_admin": False},
        {"id": "E", "name": "Neutralizar o software do fabricante",
         "state": "conflict" if _oem_power_software() else "off",
         "detail": ("O AZOR identifica quem está competindo pelo controle e mostra o que fazer. "
                    "Ele não desinstala nem desativa serviço de fabricante sozinho, porque isso "
                    "costuma levar junto o controle de ventoinha e o perfil térmico."),
         "cost": "Depende de você abrir o app do fabricante e escolher lá o perfil equivalente.",
         "action_on": "", "action_off": "", "requires_admin": False},
        {"id": "F", "name": "Guardião em sessão",
         "state": "on" if wd.get("active") else "off",
         "detail": (f"Reverte trocas em até 2 s enquanto o AZOR está aberto. "
                    f"{wd.get('reverts', 0)} reversão(ões) nesta sessão."),
         "cost": "Só vale enquanto o app está aberto. Para valer com o AZOR fechado, use a camada C.",
         "action_on": "power_watchdog_on", "action_off": "power_watchdog_off",
         "requires_admin": False},
    ]
