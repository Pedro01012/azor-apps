"""Preferências do Windows e itens avançados vindos do WinUtil.

Nada daqui entra no BOOST sozinho, com duas exceções declaradas na política
(finalizar tarefa pela barra e o atalho de teclas de aderência, que evitam
perder o foco no jogo). O resto é gosto pessoal ou tem custo que o usuário
precisa escolher: cada item é um interruptor na tela Tweaks, e volta com outro.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from .base import OptimizationTask
from .regtweak import RegSpec, V, compile_specs

MODULE = {
    "id": "prefs",
    "label": "Preferências do Windows",
    "description": "Aparência, barra de tarefas, Explorador e itens avançados. Tudo opcional.",
    "automatic": False,
}

ADV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def _admin(core, ctx):
    if not core.is_admin():
        return False, "Este ajuste grava configurações do sistema e exige o AZOR como administrador."
    return True, "Privilégio de administrador confirmado."


def _win11(min_build: int = 22000):
    def check(core, ctx):
        build = int((ctx.get("windows") or {}).get("build") or 0)
        if build and build < min_build:
            return False, "Recurso de uma versão mais nova do Windows 11; não existe neste PC."
        return True, "Versão do Windows compatível."
    return check


def _both(*checks):
    def run(core, ctx):
        detail = ""
        for check in checks:
            ok, detail = check(core, ctx)
            if not ok:
                return ok, detail
        return True, detail
    return run


def _pref(id, name, values, description, trade_off, *, category="Preferências", compatible=None,
          restart=False, restart_note="", metric="", risk="low", tags=("ui",), automatic=False):
    return RegSpec(id=id, name=name, category=category, profiles=("competitive",), values=values,
                   description=description, source="Mesma chave que a tela correspondente do Windows grava.",
                   trade_off=trade_off, metric=metric, risk=risk, restart=restart, restart_note=restart_note,
                   compatible=compatible, tags=tags, automatic=automatic)


SPECS = [
    _pref("end_task_taskbar", "Finalizar tarefa pelo botão direito na barra",
          [V("HKCU", ADV + r"\TaskbarDeveloperSettings", "TaskbarEndTask", 1)],
          "Adiciona 'Finalizar tarefa' ao clicar com o botão direito num programa na barra de tarefas. "
          "Fecha jogo travado na hora, sem abrir o Gerenciador de Tarefas.",
          "Nenhum.", compatible=_win11(22631), automatic=True, tags=("ui", "gaming")),
    _pref("dark_mode", "Tema escuro no Windows",
          [V("HKCU", PERSONALIZE, "AppsUseLightTheme", 0), V("HKCU", PERSONALIZE, "SystemUsesLightTheme", 0)],
          "Deixa o Windows e os apps no modo escuro.", "Só aparência."),
    _pref("show_extensions", "Mostrar extensões dos arquivos",
          [V("HKCU", ADV, "HideFileExt", 0)],
          "Mostra o final do nome dos arquivos (.exe, .zip, .png). Ajuda a não abrir vírus disfarçado.",
          "Só aparência."),
    _pref("show_hidden_files", "Mostrar arquivos ocultos",
          [V("HKCU", ADV, "Hidden", 1)],
          "Mostra pastas e arquivos ocultos no Explorador (como AppData, onde ficam configs de jogos).",
          "Aparecem arquivos do sistema que não devem ser apagados."),
    _pref("numlock_on", "Num Lock ligado ao entrar no Windows",
          [V("HKCU", r"Control Panel\Keyboard", "InitialKeyboardIndicators", "2")],
          "O teclado numérico já começa ligado.", "Nenhum."),
    _pref("taskbar_search_hidden", "Esconder a caixa de pesquisa da barra",
          [V("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode", 0)],
          "Tira a caixa de pesquisa da barra de tarefas. A pesquisa continua na tecla Windows.",
          "Só aparência."),
    _pref("taskview_hidden", "Esconder o botão Visão de Tarefas",
          [V("HKCU", ADV, "ShowTaskViewButton", 0)],
          "Tira o botão de áreas de trabalho da barra. Win+Tab continua funcionando.", "Só aparência."),
    _pref("taskbar_left", "Ícones da barra de tarefas à esquerda",
          [V("HKCU", ADV, "TaskbarAl", 0)],
          "Volta o botão Iniciar e os ícones para a esquerda, como no Windows 10.", "Só aparência.",
          compatible=_win11()),
    _pref("start_recommendations_off", "Menu Iniciar sem recomendações e arquivos recentes",
          [V("HKCU", ADV, "Start_IrisRecommendations", 0), V("HKCU", ADV, "Start_TrackDocs", 0)],
          "Limpa a área de recomendações do menu Iniciar (dicas, apps sugeridos e arquivos recentes).",
          "Arquivos recentes somem do menu Iniciar.", compatible=_win11()),
    _pref("detailed_bsod", "Tela azul com detalhes do erro",
          [V("HKLM", r"SYSTEM\CurrentControlSet\Control\CrashControl", "DisplayParameters", 1),
           V("HKLM", r"SYSTEM\CurrentControlSet\Control\CrashControl", "DisableEmoticon", 1)],
          "Se o PC der tela azul, mostra o código técnico do erro em vez do rostinho triste. "
          "Ajuda a descobrir se foi driver, memória ou overclock.", "Nenhum.", compatible=_admin),
    _pref("snap_off", "Desligar o encaixe automático de janelas",
          [V("HKCU", r"Control Panel\Desktop", "WindowArrangementActive", "0")],
          "Janela arrastada para a borda deixa de se encaixar sozinha.", "Perde o Snap do Windows."),
    _pref("lockscreen_off", "Pular a tela de bloqueio",
          [V("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\Personalization", "NoLockScreen", 1)],
          "Vai direto para a senha ao ligar o PC, sem a tela de papel de parede antes.",
          "Nenhum; a senha continua pedida.", compatible=_admin),
    _pref("login_blur_off", "Tela de login sem desfoque",
          [V("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System", "DisableAcrylicBackgroundOnLogon", 1)],
          "Mostra o papel de parede nítido na tela de senha.", "Só aparência.", compatible=_admin),
    _pref("home_gallery_off", "Explorador abre em 'Este Computador'",
          [V("HKCU", r"Software\Classes\CLSID\{f874310e-b6b7-47dc-bc84-b9e6b38f5903}", "System.IsPinnedToNameSpaceTree", 0),
           V("HKCU", r"Software\Classes\CLSID\{e88865ea-0e1c-4e20-9aa6-edcd0212c87c}", "System.IsPinnedToNameSpaceTree", 0),
           V("HKCU", ADV, "LaunchTo", 1)],
          "Tira 'Início' e 'Galeria' da lateral do Explorador e abre direto nos seus discos.",
          "Só navegação.", compatible=_win11()),
    _pref("notifications_off", "Desligar notificações e central de avisos",
          [V("HKCU", r"Software\Policies\Microsoft\Windows\Explorer", "DisableNotificationCenter", 1),
           V("HKCU", r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled", 0)],
          "Nenhum balão aparece na tela - nem no meio da partida.",
          "Você perde TODOS os avisos, inclusive do calendário e de mensagens.", tags=("ui", "gaming")),
    _pref("storage_sense_off", "Desligar o Sensor de Armazenamento",
          [V("HKCU", r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy", "01", 0)],
          "Impede o Windows de apagar arquivos sozinho (inclusive da pasta Downloads e da Lixeira).",
          "A limpeza automática deixa de rodar; use a Limpeza do AZOR."),
    _pref("location_off", "Desligar a localização do PC",
          [V("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny"),
           V("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Sensor\Overrides\{BFA794E4-F964-4FDB-90F6-51056BFE4B44}", "SensorPermissionState", 0),
           V("HKLM", r"SYSTEM\Maps", "AutoUpdateEnabled", 0)],
          "Nenhum app consegue saber onde o PC está, e os mapas param de se atualizar sozinhos.",
          "Clima, mapas e 'Encontrar meu dispositivo' deixam de saber a localização.",
          category="Privacidade", compatible=_admin, tags=("privacy",)),
    _pref("explorer_generic_folders", "Explorador sem 'adivinhar' o tipo de pasta",
          [V("HKCU", r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell",
             "FolderType", "NotSpecified")],
          "O Explorador para de ler o conteúdo das pastas para decidir se é de fotos, música ou "
          "vídeo. Pastas grandes (como a de jogos e downloads) abrem bem mais rápido.",
          "Pastas deixam de ter visual especial de fotos/música e o agrupamento automático some. "
          "Vale depois de sair e entrar no Windows.", restart=True,
          restart_note="Vale depois de sair e entrar no Windows."),
    _pref("ipv4_preferred", "Preferir IPv4 em vez de IPv6",
          [V("HKLM", r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents", 0x20)],
          "Faz o Windows usar IPv4 primeiro. Resolve internet lenta ou instável em redes onde o "
          "IPv6 do provedor está mal configurado. Em rede boa, não muda o ping.",
          "Nenhum na maioria das redes. Exige reiniciar.", category="Rede", compatible=_admin,
          restart=True, tags=("network",)),
]

TASKS, KEYS = compile_specs(MODULE["id"], SPECS)


# ---------------------------------------------------------------------------
# Menu de contexto clássico (Windows 11)
# ---------------------------------------------------------------------------
CLASSIC_MENU_KEY = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"


def _classic_menu_task():
    def state(core) -> bool:
        winreg = core.winreg
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASSIC_MENU_KEY + r"\InprocServer32") as k:
                value, _ = winreg.QueryValueEx(k, "")
                return value == ""
        except OSError:
            return False

    def apply(core, ctx):
        winreg = core.winreg
        if winreg is None:
            return False, "Windows only"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CLASSIC_MENU_KEY + r"\InprocServer32", 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "")
        ok = state(core)
        return ok, ("Menu clássico gravado e relido. Vale depois de reiniciar o Explorador ou o PC."
                    if ok else "A chave não foi confirmada.")

    def verify(core, ctx):
        ok = state(core)
        return ok, "Menu clássico ativo." if ok else "Menu do Windows 11 ativo."

    def revert(core, ctx):
        winreg = core.winreg
        if winreg is None:
            return False, "Windows only"
        for sub in (CLASSIC_MENU_KEY + r"\InprocServer32", CLASSIC_MENU_KEY):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass
            except OSError as exc:
                return False, f"Não foi possível remover a chave: {exc}"
        ok = not state(core)
        return ok, ("Menu do Windows 11 de volta. Vale depois de reiniciar o Explorador." if ok
                    else "A chave continua lá.")

    return OptimizationTask(
        "classic_context_menu", "Menu do botão direito completo (clássico)", MODULE["id"], "Preferências",
        ("competitive",), description="Volta o menu do botão direito completo no Explorador, sem precisar "
        "clicar em 'Mostrar mais opções'.", apply=apply, verify=verify, revert=revert,
        compatible=_win11(), tags=("ui",), automatic=False,
        source="Chave CLSID {86ca1aa0-34aa-4e8b-a509-50c905bae2a2} em HKCU, a mesma que o WinUtil usa.",
        trade_off="Só aparência. Vale depois de reiniciar o Explorador ou o PC.")


# ---------------------------------------------------------------------------
# Armazenamento reservado e BitLocker (vindos do WinUtil)
# ---------------------------------------------------------------------------

def _reserved_storage_task():
    def read(core) -> str:
        try:
            return str(core.powershell("(Get-WindowsReservedStorageState).ReservedStorageState", timeout=40)).strip()
        except Exception:
            return ""

    def compat(core, ctx):
        ok, detail = _admin(core, ctx)
        if not ok:
            return ok, detail
        now = read(core)
        if not now:
            return False, "O estado do armazenamento reservado não pôde ser lido neste Windows."
        if now.lower() == "disabled":
            return False, "O armazenamento reservado já está desligado."
        return True, "Armazenamento reservado ligado (7 a 10 GB guardados pelo Windows)."

    def apply(core, ctx):
        _remember(core, "reserved_storage", read(core))
        try:
            core.powershell("Set-WindowsReservedStorageState -State Disabled -ErrorAction Stop", timeout=120)
        except Exception as exc:
            return False, f"O Windows recusou: {exc}. Termine atualizações pendentes e tente de novo."
        return verify(core, ctx)

    def verify(core, ctx):
        ok = read(core).lower() == "disabled"
        return ok, "Armazenamento reservado desligado." if ok else "O Windows ainda reserva o espaço."

    def revert(core, ctx):
        try:
            core.powershell("Set-WindowsReservedStorageState -State Enabled -ErrorAction Stop", timeout=120)
        except Exception as exc:
            return False, f"O Windows recusou religar: {exc}"
        ok = read(core).lower() == "enabled"
        return ok, "Armazenamento reservado religado." if ok else "Não confirmado."

    return OptimizationTask(
        "reserved_storage_off", "Liberar o espaço reservado pelo Windows", MODULE["id"], "Espaço em disco",
        ("competitive",), risk="medium", automatic=False,
        description="O Windows guarda de 7 a 10 GB do disco para as próprias atualizações. Desligar "
                    "devolve esse espaço - útil em SSD pequeno lotado de jogos.",
        apply=apply, verify=verify, revert=revert, compatible=compat, tags=("disk",),
        source="Set-WindowsReservedStorageState (módulo DISM do PowerShell), Microsoft Learn.",
        trade_off="Uma atualização grande do Windows pode falhar por falta de espaço. Religue antes "
                  "de atualizar a versão do Windows.",
        metric="Espaço livre no disco do sistema")


def _bitlocker_task():
    def read(core) -> Dict[str, Any]:
        try:
            data = core.powershell_json(
                "$v=Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction Stop; "
                "[pscustomobject]@{Status=[string]$v.VolumeStatus;Protection=[string]$v.ProtectionStatus;"
                "Percent=$v.EncryptionPercentage}", timeout=40)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def compat(core, ctx):
        ok, detail = _admin(core, ctx)
        if not ok:
            return ok, detail
        st = read(core)
        if not st:
            return False, "O BitLocker não está disponível nesta edição do Windows ou não pôde ser lido."
        if st.get("Status") in ("FullyDecrypted", "DecryptionInProgress"):
            return False, "O disco do Windows não está criptografado."
        return True, f"Disco do Windows criptografado ({st.get('Percent')}%)."

    def apply(core, ctx):
        try:
            core.powershell("Disable-BitLocker -MountPoint $env:SystemDrive -ErrorAction Stop | Out-Null", timeout=120)
        except Exception as exc:
            return False, f"O Windows recusou: {exc}"
        return verify(core, ctx)

    def verify(core, ctx):
        st = read(core)
        ok = st.get("Status") in ("FullyDecrypted", "DecryptionInProgress")
        return ok, ("Descriptografia iniciada; ela continua sozinha em segundo plano." if ok
                    else "O disco continua criptografado.")

    return OptimizationTask(
        "bitlocker_off", "Desligar a criptografia do disco (BitLocker)", MODULE["id"], "Avançado",
        ("competitive",), risk="high", automatic=False, reversible=False,
        description="Com o BitLocker, tudo que o jogo lê e grava passa por criptografia. Em parte dos "
                    "SSDs isso derruba a velocidade de disco. Desligar descriptografa o disco inteiro.",
        apply=apply, verify=verify, revert=None, compatible=compat, tags=("disk", "security"),
        source="Disable-BitLocker (módulo BitLocker do PowerShell), Microsoft Learn.",
        trade_off="SE O PC FOR ROUBADO, os arquivos ficam legíveis. A descriptografia leva de minutos a "
                  "horas. Para religar: Configurações > Privacidade e segurança > Criptografia do "
                  "dispositivo.",
        metric="Velocidade de leitura e escrita do SSD")


PREFS_STATE = "prefs_state.json"


def _remember(core, key: str, value: Any) -> None:
    path = Path(core.DATA_DIR) / PREFS_STATE
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    if key not in data:
        data[key] = value
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tasks():
    return list(TASKS) + [_classic_menu_task(), _reserved_storage_task(), _bitlocker_task()]
