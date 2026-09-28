"""Windows Leve: tira do caminho tudo que roda sem o usuário pedir.

Veio do WinUtil (telemetria, Edge, IA, recursos de consumidor, serviços) e foi
reescrito no contrato do AZOR: cada item le o estado, grava, rele e sabe voltar.

O criterio para entrar aqui e um so: o item acorda CPU, disco ou rede em
segundo plano - ou instala coisa sozinho - e nenhum jogo depende dele.

O que este módulo se recusa a tocar, e por que:
  * Xbox (XblAuthManager, XblGameSave, XboxNetApiSvc, GamingServices): login
    e save de jogo do Game Pass e de varios jogos da Microsoft.
  * Anti-cheat (vgc, EasyAntiCheat, BEService, FACEIT): o jogo não abre.
  * iphlpsvc: e ele que mantem o Teredo da rede Xbox (chat de festa).
  * SysMain e Prefetcher: desligar deixa todo programa abrindo do zero.
  * SharedAccess: o ponto de acesso movel do Windows depende dele.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base import OptimizationTask
from .regtweak import RegSpec, V, compile_specs

MODULE = {
    "id": "lite",
    "label": "Windows Leve",
    "description": "Serviços, tarefas agendadas, telemetria e recursos que rodam sozinhos e pesam no PC.",
    "automatic": True,
}

POLICIES = r"SOFTWARE\Policies\Microsoft"
EDGE = POLICIES + r"\Edge"
SERVICES_ROOT = r"SYSTEM\CurrentControlSet\Services"


def _admin(core, ctx):
    if not core.is_admin():
        return False, "Este ajuste grava configurações do sistema e exige o AZOR como administrador."
    return True, "Privilégio de administrador confirmado."


def _win11(core, ctx):
    ok, detail = _admin(core, ctx)
    if not ok:
        return ok, detail
    build = int((ctx.get("windows") or {}).get("build") or 0)
    if build and build < 22000:
        return False, "Recurso do Windows 11; este PC está no Windows 10 e não tem o que desligar aqui."
    return True, detail


SPECS = [
    RegSpec(
        id="consumer_features_off",
        name="Bloquear apps promocionais que o Windows instala sozinho",
        category="Leve / Apps automáticos",
        profiles=("competitive",),
        values=[
            V("HKLM", POLICIES + r"\Windows\CloudContent", "DisableWindowsConsumerFeatures", 1),
            V("HKLM", POLICIES + r"\Windows\CloudContent", "DisableSoftLanding", 1),
            V("HKLM", POLICIES + r"\Windows\CloudContent", "DisableCloudOptimizedContent", 1),
        ],
        compatible=_admin,
        description="Impede o Windows de baixar e instalar sozinho jogos e apps de parceiros "
                    "(Candy Crush, TikTok, Spotify de propaganda) e de mostrar dicas promocionais.",
        source="Políticas DisableWindowsConsumerFeatures, DisableSoftLanding e "
               "DisableCloudOptimizedContent (Componentes do Windows > Conteúdo da Nuvem).",
        trade_off="Nenhum para quem joga. Em edições Home o Windows pode ignorar parte da política.",
        metric="Processos e instalações em segundo plano",
        tags=("background", "policy"),
    ),
    RegSpec(
        id="copilot_recall_off",
        name="Desligar Copilot, Recall e IA do Windows",
        category="Leve / IA",
        profiles=("competitive",),
        values=[
            V("HKLM", POLICIES + r"\Windows\WindowsAI", "AllowRecallEnablement", 0),
            V("HKLM", POLICIES + r"\Windows\WindowsAI", "DisableAIDataAnalysis", 1),
            V("HKLM", POLICIES + r"\Windows\WindowsAI", "DisableClickToDo", 1),
            V("HKCU", r"Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1),
            V("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint", "DisableCocreator", 1),
            V("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint", "DisableGenerativeFill", 1),
            V("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint", "DisableImageCreator", 1),
            V("HKLM", r"SOFTWARE\Policies\WindowsNotepad", "DisableAIFeatures", 1),
        ],
        compatible=_admin,
        description="O Recall tira foto da tela o tempo todo e analisa com IA; o Copilot e o "
                    "Click to Do ficam residentes. Estas são as políticas oficiais que desligam "
                    "tudo isso e apagam os snapshots do Recall.",
        source="Políticas WindowsAI (AllowRecallEnablement, DisableAIDataAnalysis, DisableClickToDo), "
               "TurnOffWindowsCopilot e as políticas de IA do Paint e do Bloco de Notas.",
        trade_off="Você perde o Copilot, o Recall e os recursos de IA do Paint e do Bloco de Notas.",
        metric="CPU, disco e RAM em repouso",
        tags=("background", "policy", "ai"),
    ),
    RegSpec(
        id="activity_history_off",
        name="Desligar o histórico de atividades",
        category="Leve / Privacidade",
        profiles=("competitive",),
        values=[
            V("HKLM", POLICIES + r"\Windows\System", "EnableActivityFeed", 0),
            V("HKLM", POLICIES + r"\Windows\System", "PublishUserActivities", 0),
            V("HKLM", POLICIES + r"\Windows\System", "UploadUserActivities", 0),
        ],
        compatible=_admin,
        description="O Windows registra cada programa e arquivo que você abre para montar uma "
                    "linha do tempo e sincronizar com a nuvem. Desligar tira essa gravação contínua.",
        source="Políticas EnableActivityFeed, PublishUserActivities e UploadUserActivities "
               "(Sistema > Políticas do SO).",
        trade_off="A linha do tempo de atividades deixa de existir.",
        metric="Escritas de disco em repouso",
        tags=("privacy", "policy"),
    ),
    RegSpec(
        id="telemetry_full_off",
        name="Cortar a telemetria e os anúncios do usuário",
        category="Leve / Privacidade",
        profiles=("competitive",),
        values=[
            V("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0),
            V("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0),
            V("HKCU", r"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", 0),
            V("HKCU", r"Software\Microsoft\Input\TIPC", "Enabled", 0),
            V("HKCU", r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1),
            V("HKCU", r"Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", 1),
            V("HKCU", r"Software\Microsoft\InputPersonalization\TrainedDataStore", "HarvestContacts", 0),
            V("HKCU", r"Software\Microsoft\Personalization\Settings", "AcceptedPrivacyPolicy", 0),
            V("HKCU", r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0),
            V("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
              "POWERSHELL_TELEMETRY_OPTOUT", "1"),
        ],
        compatible=_admin,
        description="Desliga o ID de anúncios, as experiências personalizadas, o envio de digitação "
                    "e voz para a Microsoft e os pedidos de avaliação que aparecem na tela.",
        source="Configurações > Privacidade e segurança > Geral, Fala, Personalização de escrita e "
               "Diagnóstico e comentários - as mesmas chaves que essas telas gravam.",
        trade_off="Sugestões personalizadas e o reconhecimento de fala online deixam de funcionar.",
        metric="Uso de rede em repouso",
        tags=("privacy", "telemetry"),
        relations=[{"kind": "combina", "id": "telemetry_tasks_off",
                    "note": "Este desliga a coleta; o outro desliga as tarefas que enviam."}],
    ),
    RegSpec(
        id="edge_background_off",
        name="Impedir o Edge de rodar escondido",
        category="Leve / Edge",
        profiles=("competitive",),
        values=[
            V("HKLM", EDGE, "StartupBoostEnabled", 0),
            V("HKLM", EDGE, "BackgroundModeEnabled", 0),
            V("HKLM", EDGE, "HideFirstRunExperience", 1),
            V("HKLM", EDGE, "ShowRecommendationsEnabled", 0),
            V("HKLM", EDGE, "EdgeShoppingAssistantEnabled", 0),
            V("HKLM", EDGE, "ShowMicrosoftRewards", 0),
            V("HKLM", EDGE, "EdgeCollectionsEnabled", 0),
            V("HKLM", EDGE, "MicrosoftEdgeInsiderPromotionEnabled", 0),
            V("HKLM", EDGE, "DefaultBrowserSettingsCampaignEnabled", 0),
            V("HKLM", EDGE, "PersonalizationReportingEnabled", 0),
            V("HKLM", EDGE, "UserFeedbackAllowed", 0),
            V("HKLM", EDGE, "DiagnosticData", 0),
            V("HKLM", POLICIES + r"\EdgeUpdate", "CreateDesktopShortcutDefault", 0),
        ],
        compatible=_admin,
        description="O Edge abre sozinho no boot (Aumento de Inicialização) e continua rodando "
                    "depois de fechado (Modo em segundo plano). Isso são processos e RAM presos "
                    "mesmo para quem nunca usa o Edge. Também corta propaganda e telemetria dele.",
        source="Políticas do Microsoft Edge: StartupBoostEnabled, BackgroundModeEnabled e as de "
               "recomendação, compras, Rewards e dados de diagnóstico (Microsoft Learn).",
        trade_off="O Edge abre um pouco mais devagar na primeira vez e passa a mostrar "
                  "'gerenciado pela sua organização' - é o aviso normal de política aplicada.",
        metric="Processos e RAM em repouso",
        tags=("background", "policy", "edge"),
    ),
    RegSpec(
        id="bing_search_off",
        name="Busca do menu Iniciar só no PC (sem Bing)",
        category="Leve / Pesquisa",
        profiles=("competitive",),
        values=[
            V("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0),
            V("HKCU", r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 1),
        ],
        description="Cada tecla digitada no menu Iniciar ia para a internet buscar no Bing. Assim a "
                    "busca fica só nos seus programas e arquivos: mais rápida e sem rede.",
        source="BingSearchEnabled e a política DisableSearchBoxSuggestions (Explorador de Arquivos).",
        trade_off="Resultados da web deixam de aparecer no menu Iniciar.",
        metric="Tempo de resposta do menu Iniciar",
        tags=("background", "search"),
    ),
    RegSpec(
        id="device_metadata_off",
        name="Não baixar apps de fabricante ao conectar aparelhos",
        category="Leve / Apps automáticos",
        profiles=("competitive",),
        values=[V("HKLM", POLICIES + r"\Windows\Device Metadata", "PreventDeviceMetadataFromNetwork", 1)],
        compatible=_admin,
        description="Impede o Windows de baixar sozinho programas e propagandas de fabricante quando "
                    "você conecta um monitor, mouse ou headset novo.",
        source="Política PreventDeviceMetadataFromNetwork (Sistema > Instalação de Dispositivo).",
        trade_off="O ícone personalizado do aparelho pode não aparecer em Dispositivos. O driver "
                  "continua vindo normalmente.",
        metric="Instalações em segundo plano",
        tags=("background", "policy"),
    ),
    RegSpec(
        id="sticky_keys_off",
        name="Desligar o atalho de Teclas de Aderência",
        category="Leve / Interrupções",
        profiles=("competitive",),
        values=[
            V("HKCU", r"Control Panel\Accessibility\StickyKeys", "Flags", "506"),
            V("HKCU", r"Control Panel\Accessibility\ToggleKeys", "Flags", "58"),
            V("HKCU", r"Control Panel\Accessibility\Keyboard Response", "Flags", "122"),
        ],
        description="Apertar Shift 5 vezes (ou segurar) no meio da partida abre a janela das Teclas "
                    "de Aderência e tira o foco do jogo. Isto desliga só o ATALHO; o recurso "
                    "continua disponível em Configurações.",
        source="HKCU\\Control Panel\\Accessibility (StickyKeys, ToggleKeys e Keyboard Response): os "
               "mesmos valores de desmarcar 'Permitir que a tecla de atalho inicie' em Acessibilidade.",
        trade_off="Quem usa as Teclas de Aderência precisa ligá-las por Configurações > Acessibilidade.",
        metric="Perda de foco no meio da partida",
        tags=("gaming", "input"),
    ),
]

TASKS, KEYS = compile_specs(MODULE["id"], SPECS)


# ---------------------------------------------------------------------------
# Serviços que rodam sem ninguém pedir
#
# Passam de Automático para Manual: o serviço deixa de subir no boot, mas o
# Windows ainda o inicia sozinho se algum programa precisar. É a forma segura de
# "limpar processos": nada fica quebrado, e o processo some da lista.
# ---------------------------------------------------------------------------

LITE_SERVICES: Tuple[Tuple[str, str], ...] = (
    ("MapsBroker", "Gerenciador de mapas baixados"),
    ("TrkWks", "Rastreamento de links distribuídos"),
    ("PcaSvc", "Assistente de compatibilidade de programas"),
    ("InventorySvc", "Inventário e avaliação de compatibilidade"),
    ("WpcMonSvc", "Controle dos pais"),
    ("RetailDemo", "Modo de demonstração de loja"),
    ("edgeupdate", "Atualizador do Edge"),
    ("edgeupdatem", "Atualizador do Edge (tarefa)"),
    ("gupdate", "Atualizador do Google"),
    ("gupdatem", "Atualizador do Google (tarefa)"),
    ("brave", "Atualizador do Brave"),
    ("bravem", "Atualizador do Brave (tarefa)"),
    ("AdobeARMservice", "Atualizador do Adobe Reader"),
    ("CscService", "Arquivos Offline"),
    ("Fax", "Fax"),
    ("WMPNetworkSvc", "Compartilhamento do Windows Media Player"),
)

EXTREME_SERVICES: Tuple[Tuple[str, str], ...] = (
    ("WSearch", "Indexador da Pesquisa do Windows"),
    ("CDPSvc", "Plataforma de Dispositivos Conectados"),
)


def _service_keys(rows) -> List[Tuple[str, str, str]]:
    return [("HKLM", SERVICES_ROOT + "\\" + name, "Start") for name, _ in rows]


KEYS["services_lite"] = _service_keys(LITE_SERVICES)
KEYS["services_extreme"] = _service_keys(EXTREME_SERVICES)


def _service_task(task_id: str, name: str, rows, description: str, trade_off: str, extreme: bool):
    def automatic_now(core) -> List[Tuple[str, str]]:
        found = []
        for service, label in rows:
            state = core.service_state(service)
            if state.get("exists") and int(state.get("start") or 0) == 2:
                found.append((service, label))
        return found

    def compat(core, ctx):
        ok, detail = _admin(core, ctx)
        if not ok:
            return ok, detail
        pending = automatic_now(core)
        if not pending:
            return False, "Nenhum desses serviços está em inicialização automática neste PC."
        return True, (f"{len(pending)} serviço(s) subindo sozinho(s) no boot: "
                      + ", ".join(label for _, label in pending[:4])
                      + ("..." if len(pending) > 4 else "."))

    def apply(core, ctx):
        done, failed = [], []
        for service, label in automatic_now(core):
            ok, detail = core.set_service_start_verified(service, "Manual")
            if ok:
                done.append(label)
                # Parar agora tira o processo da lista sem esperar o próximo boot.
                # Se o Windows recusar (algo está usando), fica para o boot.
                try:
                    core.run_hidden(["sc", "stop", service], timeout=15)
                except Exception:
                    pass
            else:
                failed.append(f"{label}: {detail}")
        if failed:
            return False, "Não confirmado: " + "; ".join(failed[:3])
        return True, f"{len(done)} serviço(s) em Manual: " + ", ".join(done) + "."

    def verify(core, ctx):
        pending = automatic_now(core)
        ok = not pending
        return ok, ("Nenhum desses serviços sobe mais sozinho no boot." if ok
                    else "Ainda automáticos: " + ", ".join(label for _, label in pending))

    def revert(core, ctx):
        return core.revert_registry_from_baseline(_service_keys(rows), task_id)

    return OptimizationTask(
        task_id, name, MODULE["id"], "Leve / Serviços", ("competitive",),
        risk="medium" if extreme else "low", description=description,
        apply=apply, verify=verify, revert=revert, compatible=compat,
        tags=("service", "background"), registry_keys=tuple(_service_keys(rows)),
        source="Tipo de inicialização de serviço (sc config start= demand) - o mesmo que "
               "services.msc grava. Manual não desliga: o Windows inicia o serviço se algo pedir.",
        trade_off=trade_off, metric="Processos e RAM em repouso",
    )


# ---------------------------------------------------------------------------
# Tarefas agendadas de telemetria
#
# O CompatTelRunner.exe (Microsoft Compatibility Appraiser) é o campeão de
# "o PC travou do nada": ele varre o disco inteiro de tempos em tempos para
# decidir se o PC aguenta a próxima versão do Windows.
# ---------------------------------------------------------------------------

TELEMETRY_TASKS: Tuple[Tuple[str, str], ...] = (
    (r"\Microsoft\Windows\Application Experience\\", "Microsoft Compatibility Appraiser"),
    (r"\Microsoft\Windows\Application Experience\\", "Microsoft Compatibility Appraiser Exp"),
    (r"\Microsoft\Windows\Application Experience\\", "ProgramDataUpdater"),
    (r"\Microsoft\Windows\Application Experience\\", "MareBackup"),
    (r"\Microsoft\Windows\Autochk\\", "Proxy"),
    (r"\Microsoft\Windows\Customer Experience Improvement Program\\", "Consolidator"),
    (r"\Microsoft\Windows\Customer Experience Improvement Program\\", "UsbCeip"),
    (r"\Microsoft\Windows\DiskDiagnostic\\", "Microsoft-Windows-DiskDiagnosticDataCollector"),
    (r"\Microsoft\Windows\Feedback\Siuf\\", "DmClient"),
    (r"\Microsoft\Windows\Feedback\Siuf\\", "DmClientOnScenarioDownload"),
    (r"\Microsoft\Windows\Windows Error Reporting\\", "QueueReporting"),
    (r"\Microsoft\Windows\Maps\\", "MapsUpdateTask"),
    (r"\Microsoft\Windows\Maps\\", "MapsToastTask"),
)
TASKS_BASELINE = "lite_tasks_baseline.json"


def _task_rows() -> List[Dict[str, str]]:
    # O raw string com duas barras no fim vira uma barra so ao normalizar.
    return [{"path": path.rstrip("\\") + "\\", "name": name} for path, name in TELEMETRY_TASKS]


def scheduled_task_states(core) -> List[Dict[str, Any]]:
    """Estado de cada tarefa: 1 = desabilitada, 3 = pronta, 4 = rodando, None = não existe."""
    items = ", ".join("@{P=" + json.dumps(r["path"]) + ";N=" + json.dumps(r["name"]) + "}"
                      for r in _task_rows())
    script = ("$list=@(" + items + "); foreach($i in $list){ "
              "$t=Get-ScheduledTask -TaskPath $i.P -TaskName $i.N -ErrorAction SilentlyContinue; "
              "[pscustomobject]@{Path=$i.P;Name=$i.N;State=$(if($t){[int]$t.State}else{$null})} }")
    data = core.powershell_json(script, timeout=45)
    if isinstance(data, dict):
        data = [data]
    return [{"path": str(d.get("Path")), "name": str(d.get("Name")), "state": d.get("State")}
            for d in (data or []) if isinstance(d, dict)]


def _tasks_baseline_path(core) -> Path:
    return Path(core.DATA_DIR) / TASKS_BASELINE


def _remember_task_states(core, rows) -> None:
    """Grava o estado anterior UMA vez por tarefa, como o baseline de registro."""
    path = _tasks_baseline_path(core)
    try:
        saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        saved = {}
    changed = False
    for row in rows:
        key = row["path"] + row["name"]
        if key not in saved and row.get("state") is not None:
            saved[key] = row["state"]
            changed = True
    if changed:
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")


def _ps_task(verb: str, row: Dict[str, str]) -> str:
    return (f"{verb}-ScheduledTask -TaskPath {json.dumps(row['path'])} -TaskName {json.dumps(row['name'])} "
            "-ErrorAction Stop | Out-Null")


def _telemetry_tasks_task():
    def compat(core, ctx):
        ok, detail = _admin(core, ctx)
        if not ok:
            return ok, detail
        try:
            rows = scheduled_task_states(core)
        except Exception as exc:
            return False, f"As tarefas agendadas não puderam ser lidas: {exc}"
        active = [r for r in rows if r["state"] not in (None, 1)]
        if not active:
            return False, "As tarefas de telemetria já estão desativadas ou não existem neste Windows."
        return True, f"{len(active)} tarefa(s) de telemetria agendada(s) e ativa(s)."

    def apply(core, ctx):
        rows = scheduled_task_states(core)
        _remember_task_states(core, rows)
        active = [r for r in rows if r["state"] not in (None, 1)]
        if not active:
            return True, "Nada a desativar."
        script = "; ".join(_ps_task("Disable", r) for r in active) + "; 'OK'"
        try:
            core.powershell(script, timeout=60)
        except Exception as exc:
            return False, f"O Windows recusou desativar uma tarefa: {exc}"
        return True, f"{len(active)} tarefa(s) desativada(s)."

    def verify(core, ctx):
        rows = scheduled_task_states(core)
        active = [r["name"] for r in rows if r["state"] not in (None, 1)]
        ok = not active
        return ok, ("Todas as tarefas de telemetria relidas como desativadas." if ok
                    else "Ainda ativas: " + ", ".join(active))

    def revert(core, ctx):
        path = _tasks_baseline_path(core)
        try:
            saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            saved = {}
        if not saved:
            return False, "O AZOR não registrou o estado anterior das tarefas; nada foi alterado."
        to_enable = [r for r in _task_rows() if saved.get(r["path"] + r["name"]) not in (None, 1)]
        if not to_enable:
            return True, "Todas as tarefas já estavam desativadas antes do AZOR."
        script = "; ".join(_ps_task("Enable", r) for r in to_enable) + "; 'OK'"
        try:
            core.powershell(script, timeout=60)
        except Exception as exc:
            return False, f"O Windows recusou reativar uma tarefa: {exc}"
        rows = {r["path"] + r["name"]: r["state"] for r in scheduled_task_states(core)}
        missing = [r["name"] for r in to_enable if rows.get(r["path"] + r["name"]) == 1]
        return (not missing), ("Tarefas reativadas e relidas." if not missing
                               else "Não reativadas: " + ", ".join(missing))

    return OptimizationTask(
        "telemetry_tasks_off", "Desligar as tarefas agendadas de telemetria", MODULE["id"],
        "Leve / Tarefas agendadas", ("competitive",), risk="low",
        description="Desativa as tarefas que acordam sozinhas para varrer o disco e enviar dados "
                    "(CompatTelRunner, CEIP, relatórios de erro, diagnóstico de disco). São a causa "
                    "clássica de 'o PC engasgou do nada' com o disco em 100%.",
        apply=apply, verify=verify, revert=revert, compatible=compat,
        tags=("background", "telemetry", "tasks"),
        source="Agendador de Tarefas > Microsoft > Windows (Application Experience, Customer Experience "
               "Improvement Program, Feedback, Windows Error Reporting, DiskDiagnostic, Maps).",
        trade_off="Relatórios de erro e de compatibilidade deixam de ser enviados à Microsoft. "
                  "Windows Update e segurança não dependem delas.",
        metric="Picos de CPU e disco em repouso",
    )


def tasks():
    return list(TASKS) + [
        _telemetry_tasks_task(),
        _service_task(
            "services_lite", "Tirar do boot os serviços que só pesam", LITE_SERVICES,
            "Serviços de mapas, compatibilidade, controle dos pais, arquivos offline e os "
            "atualizadores do Edge, Google, Brave e Adobe sobem junto com o Windows e ficam na "
            "memória. Em Manual eles saem do boot e só rodam se algo precisar.",
            "Os atualizadores passam a rodar quando você abre o programa, em vez de o tempo todo.",
            extreme=False),
        _service_task(
            "services_extreme", "Desligar o indexador da pesquisa e o serviço de dispositivos", EXTREME_SERVICES,
            "O indexador da pesquisa lê o disco inteiro de tempos em tempos para montar o índice, "
            "e a Plataforma de Dispositivos Conectados fica residente para o Vincular ao Celular.",
            "A busca de arquivos no menu Iniciar e no Explorador fica mais lenta (continua "
            "funcionando, sem índice). O Vincular ao Celular e o compartilhamento por proximidade "
            "podem parar.",
            extreme=True),
    ]
