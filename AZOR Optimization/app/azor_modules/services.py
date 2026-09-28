"""Servicos do Windows, um de cada vez e com a conta na mesa.

A pratica comum do genero -- desligar quarenta serviços de uma vez porque uma
lista da internet mandou -- e a razao de metade dos PCs que chegam "otimizados"
chegarem também sem impressora, sem busca e sem loja. Este módulo faz o oposto:
são poucos itens, cada um sabe dizer o que deixa de funcionar, cada um so aparece
quando faz sentido nesta máquina, e cada um volta com um clique.

O que este módulo se RECUSA a desligar, e por que:
  * WSearch (Windows Search) - quebra a busca do menu Iniciar e do Explorer, e o
    indexador já não roda durante jogo em tela cheia.
  * Audiosrv, AudioEndpointBuilder - sem áudio não ha jogo.
  * BITS, wuauserv - o Windows volta a liga-los sozinho, e sem eles o PC para de
    receber correcao de segurança.
  * Servicos de anticheat e de fabricante de GPU - desligar quebra o jogo.
"""
from __future__ import annotations

from .base import OptimizationTask, internal_disk_media

MODULE = {
    "id": "services",
    "label": "Serviços",
    "description": "Poucos serviços, escolhidos por medição e não por lista da internet. Cada um declara o que para de funcionar.",
    "automatic": True,
}

SERVICES_ROOT = r"SYSTEM\CurrentControlSet\Services"

# Declarado aqui, capturado pelo baseline automaticamente: o tipo de
# inicializacao de um servico e um DWORD de registro como qualquer outro.
KEYS = {
    "diagtrack_off": [("HKLM", SERVICES_ROOT + r"\DiagTrack", "Start")],
    "sysmain_ssd_off": [("HKLM", SERVICES_ROOT + r"\SysMain", "Start")],
    "spooler_off": [("HKLM", SERVICES_ROOT + r"\Spooler", "Start")],
}


def _admin(core):
    return core.is_admin()


def _service_task(service: str, label: str) -> str:
    return f"{label} ({service})"


def _revert_service(service: str, task_id: str):
    def run(core, ctx):
        entry = core.baseline_registry_entry("HKLM", SERVICES_ROOT + "\\" + service, "Start")
        if entry is None or not entry.get("exists"):
            return False, (f"O baseline não registrou o tipo de inicialização anterior de {service}; "
                           "nada foi alterado por suposição.")
        label = core.SERVICE_START_NAMES.get(int(entry.get("value") or 0))
        if not label:
            return False, f"O valor guardado para {service} não é um tipo de inicialização válido."
        return core.set_service_start_verified(service, label)
    return run


def _verify_disabled(service: str):
    def run(core, ctx):
        state = core.service_state(service)
        ok = bool(state.get("disabled"))
        return ok, (f"{service} relido como Desabilitado no registro de serviços." if ok
                    else f"{service} continua em {state.get('start_label')}.")
    return run


def _apply_disabled(service: str):
    def run(core, ctx):
        return core.set_service_start_verified(service, "Disabled")
    return run


def tasks():
    def diagtrack_compat(core, ctx):
        if not _admin(core):
            return False, "Alterar serviço exige o AZOR aberto como administrador."
        state = core.service_state("DiagTrack")
        if not state.get("exists"):
            return False, "DiagTrack não existe nesta edição do Windows; nada a fazer."
        if state.get("disabled"):
            return False, "DiagTrack já está desabilitado."
        return True, f"DiagTrack em {state.get('start_label')}; pode ser desabilitado e revertido."

    def sysmain_compat(core, ctx):
        if not _admin(core):
            return False, "Alterar serviço exige o AZOR aberto como administrador."
        state = core.service_state("SysMain")
        if not state.get("exists"):
            return False, "SysMain não existe nesta instalação; nada a fazer."
        if state.get("disabled"):
            return False, "SysMain já está desabilitado."
        # A chave lida aqui era "Média", com acento, e o storage_health() devolve
        # "Media": todo SSD caia como disco mecanico e o item nunca aparecia.
        media = internal_disk_media(core)
        if not media:
            return False, "O tipo de mídia dos discos não pode ser confirmado; o SysMain fica preservado."
        mechanical = [m for m in media if m != "SSD"]
        if mechanical:
            return False, ("Há disco não-sólido neste PC (" + ", ".join(sorted(set(mechanical))) + "). "
                           "Em HDD o SysMain ajuda de verdade no tempo de carregamento, então ele "
                           "fica preservado.")
        return True, f"{len(media)} disco(s), todos sólidos; o SysMain pode ser testado desligado."

    def spooler_compat(core, ctx):
        if not _admin(core):
            return False, "Alterar serviço exige o AZOR aberto como administrador."
        state = core.service_state("Spooler")
        if not state.get("exists"):
            return False, "O spooler de impressão não existe nesta instalação."
        if state.get("disabled"):
            return False, "O spooler já está desabilitado."
        count = core.printer_count()
        if count is None:
            return False, ("Não foi possível confirmar quantas impressoras existem. Sem essa "
                           "confirmação o AZOR não desliga o spooler.")
        if count > 0:
            return False, (f"{count} impressora(s) instalada(s). O spooler fica ligado: desligar aqui "
                           "seria trocar desempenho irrelevante por uma impressora que para de funcionar.")
        return True, "Nenhuma impressora instalada; o spooler pode ser desligado com segurança."

    return [
        OptimizationTask(
            "diagtrack_off", "Desligar a telemetria de experiência do usuário", MODULE["id"],
            "Serviços / Telemetria", ("competitive", "stream"), risk="medium",
            description="Desabilita o serviço DiagTrack, que coleta e envia dados de diagnóstico em "
                        "segundo plano. Ele acorda disco e rede em momentos que você não escolhe.",
            apply=_apply_disabled("DiagTrack"), verify=_verify_disabled("DiagTrack"),
            revert=_revert_service("DiagTrack", "diagtrack_off"), compatible=diagtrack_compat,
            tags=("service", "telemetry", "background"),
            source="Serviço 'Experiências do Usuário Conectado e Telemetria' (DiagTrack), documentado "
                   "pela Microsoft nos guias de dados de diagnóstico do Windows para empresas.",
            trade_off="O Hub de Comentários para de enviar, o programa Windows Insider deixa de "
                      "funcionar e alguns relatórios de erro não sobem. Não afeta Windows Update nem "
                      "segurança.",
            metric="Uso de disco e CPU em repouso",
        ),
        OptimizationTask(
            "sysmain_ssd_off", "Testar o PC sem o SysMain (somente SSD)", MODULE["id"],
            "Serviços / Memória", ("competitive",), risk="experimental", automatic=False,
            description="Desabilita o SysMain (antigo Superfetch). Ele só aparece quando o PC tem "
                        "apenas armazenamento sólido -- em HDD ele ajuda de verdade e fica intocado. "
                        "Mesmo em SSD, o ganho varia por máquina: aplique, jogue duas partidas e reverta "
                        "se não sentir diferença.",
            apply=_apply_disabled("SysMain"), verify=_verify_disabled("SysMain"),
            revert=_revert_service("SysMain", "sysmain_ssd_off"), compatible=sysmain_compat,
            tags=("service", "memory", "ab-test"),
            source="Serviço SysMain (Superfetch) - documentação de serviços do Windows. Em disco "
                   "sólido o pré-carregamento que ele faz tem retorno muito menor.",
            trade_off="A primeira abertura de programas grandes pode ficar mais lenta, porque o Windows "
                      "para de pré-carregar o que você costuma usar. Este item é um teste A/B, não uma "
                      "promessa: o AZOR não afirma ganho aqui.",
            metric="p99 de frametime e uso de disco em repouso",
        ),
        OptimizationTask(
            "spooler_off", "Desligar o spooler de impressão (sem impressora instalada)", MODULE["id"],
            "Serviços / Background", ("competitive",), risk="medium",
            description="Desabilita o spooler apenas em PC sem nenhuma impressora instalada. Alem de um "
                        "processo a menos em memória, ele já foi alvo de falhas de segurança conhecidas.",
            apply=_apply_disabled("Spooler"), verify=_verify_disabled("Spooler"),
            revert=_revert_service("Spooler", "spooler_off"), compatible=spooler_compat,
            tags=("service", "background", "security"),
            source="Serviço Spooler de Impressão (Spooler) - documentação de serviços do Windows.",
            trade_off="Enquanto estiver desligado, este PC não imprime e não instala impressora. Se você "
                      "for imprimir, reverta antes -- é um clique, e o AZOR guarda o valor original.",
            metric="Processos ativos em repouso",
        ),
    ]
