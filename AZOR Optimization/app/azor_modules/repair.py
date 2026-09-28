"""Reparo: desfaz o que outros "otimizadores" quebraram.

Este módulo é o oposto dos outros. Ele não melhora um Windows de fábrica — em um
PC intacto, todos os itens aqui aparecem como "nada a reparar" e o módulo fica
vazio. Ele só tem trabalho quando alguém já passou um script de internet na
máquina.

E isso é comum: HPET forçado no boot, serviço de áudio desabilitado, firewall
desligado, Proteção do Sistema off, auto-ajuste de TCP quebrado, TRIM desligado.
Nada disso dá erro. O Windows apenas fica pior em silêncio, e a culpa costuma
sobrar para o jogo.

**Reparo não tem desfazer.** O AZOR não oferece um botão para desligar o firewall
de novo, nem para forçar o HPET de volta. Cada item aqui declara `reversible=False`
e explica o porquê — e mostra o comando para quem realmente quiser.
"""
from __future__ import annotations

from .base import OptimizationTask, only_solid_state

MODULE = {
    "id": "repair",
    "label": "Reparo",
    "description": "Detecta e desfaz estragos deixados por outros otimizadores. Em um PC intacto este módulo não tem nada a fazer, e diz isso.",
    "automatic": True,
}

KEYS: dict = {}

_ALL_PROFILES = ("safe", "competitive", "campanha", "stream")


def _needs_admin_to_fix(core, found: str) -> tuple:
    """Diagnóstico primeiro, permissão depois.

    A versão anterior pedia administrador antes de olhar, e num PC saudável o
    cliente lia "exige administrador" onde a resposta certa era "está tudo bem".
    Leitura de registro, firewall e fsutil funcionam sem elevação; só a escrita
    precisa. Então o pedido de permissão só aparece quando há conserto a fazer.

    O estrago encontrado é elegível mesmo sem elevação: a interface roda como
    usuário comum e pede o UAC só na hora de consertar (todo item de reparo
    declara requires_admin). Antes, o achado confirmado virava "não verificado"
    na tela, e o botão CONSERTAR mandava fechar e reabrir o app.
    """
    if not core.is_admin():
        return True, found + " Consertar pede a autorização de administrador do Windows."
    return True, found


def tasks():
    # ---------------- overrides de temporizador no boot ----------------
    def bcd_compat(core, ctx):
        # Único caso em que a leitura também exige elevação: o bcdedit recusa
        # enumerar o {current} para um usuário comum.
        state = core.bcd_overrides()
        if not state.get("readable"):
            return False, (state.get("detail") or "As opções de boot não puderam ser lidas; nada foi alterado.")
        present = state.get("present") or []
        if not present:
            return False, "Nenhum override de temporizador no boot. Nada a reparar."
        return True, ("Encontrado no boot: " + ", ".join(present) +
                      ". Nenhuma dessas opções existe num Windows de fábrica.")

    def bcd_apply(core, ctx):
        present = (core.bcd_overrides(force=True).get("present") or [])
        if not present:
            return True, "Nenhum override para remover."
        done, failed = [], []
        for name in present:
            ok, detail = core.remove_bcd_override(name)
            (done if ok else failed).append(name if ok else f"{name} ({detail})")
        ok = bool(done) and not failed
        return ok, ((f"Removido(s) do boot e confirmado(s): {', '.join(done)}. "
                     "Só passa a valer depois de reiniciar o Windows.") if ok
                    else "Não confirmado: " + ", ".join(failed))

    def bcd_verify(core, ctx):
        state = core.bcd_overrides(force=True)
        if not state.get("readable"):
            return False, state.get("detail") or "Estado do boot não pôde ser relido."
        ok = not (state.get("present") or [])
        return ok, ("Boot relido: nenhum override de temporizador." if ok
                    else "Ainda presente(s): " + ", ".join(state["present"]))

    # ---------------- serviços essenciais ----------------
    def services_compat(core, ctx):
        broken = core.disabled_essential_services()
        if not broken:
            return False, "Nenhum serviço essencial está desabilitado. Nada a reparar."
        found = ("Desabilitado(s): " + ", ".join(f"{b['name']} ({b['breaks']})" for b in broken[:4])
                 + (f" e mais {len(broken) - 4}." if len(broken) > 4 else "."))
        return _needs_admin_to_fix(core, found)

    def services_apply(core, ctx):
        return core.restore_essential_services()

    def services_verify(core, ctx):
        broken = core.disabled_essential_services()
        ok = not broken
        return ok, ("Todos os serviços essenciais relidos com inicialização normal." if ok
                    else "Ainda desabilitado(s): " + ", ".join(b["name"] for b in broken))

    # ---------------- firewall ----------------
    def firewall_compat(core, ctx):
        state = core.firewall_state()
        if not state.get("readable"):
            return False, "O estado do firewall não pôde ser lido; nada foi alterado."
        off = state.get("disabled") or []
        if not off:
            return False, "Todos os perfis do firewall já estão ligados. Nada a reparar."
        return _needs_admin_to_fix(core, "Perfil(is) desligado(s): " + ", ".join(off) + ".")

    def firewall_apply(core, ctx):
        return core.enable_firewall_verified()

    def firewall_verify(core, ctx):
        state = core.firewall_state(force=True)
        ok = state.get("readable") and not (state.get("disabled") or [])
        return ok, ("Firewall relido: todos os perfis ligados." if ok
                    else "Ainda desligado(s): " + ", ".join(state.get("disabled") or []))

    # ---------------- proteção do sistema ----------------
    def restore_compat(core, ctx):
        state = core.system_restore_config()
        if not state.get("readable"):
            return False, state.get("detail") or "Estado não confirmado; preservado."
        if state.get("enabled"):
            return False, "Proteção do Sistema já está ligada. Nada a reparar."
        return _needs_admin_to_fix(core, state.get("detail") or "Proteção do Sistema desligada.")

    def restore_apply(core, ctx):
        return core.enable_system_restore_verified()

    def restore_verify(core, ctx):
        state = core.system_restore_config()
        ok = bool(state.get("enabled"))
        return ok, state.get("detail") or ""

    # ---------------- auto-ajuste de TCP (movido da rede) ----------------
    def autotuning_compat(core, ctx):
        state = core.tcp_global_state()
        current = core._tcp_global_lookup(state, "autotuninglevel") or ""
        if not current:
            return False, "O Windows não respondeu o nível de auto-ajuste; preservado."
        if current.strip().lower().startswith("normal"):
            return False, ("Auto-ajuste da janela de recepção já está em 'normal', que é o valor "
                           "correto. Nada a reparar.")
        return True, (f"Auto-ajuste está em '{current}'. Fora de 'normal', o download em conexão "
                      "rápida trava em uma fração da velocidade contratada.")

    def autotuning_apply(core, ctx):
        return core.set_tcp_global_verified("autotuninglevel", "normal")

    def autotuning_verify(core, ctx):
        current = core._tcp_global_lookup(core.tcp_global_state(), "autotuninglevel") or ""
        ok = current.strip().lower().startswith("normal")
        return ok, (f"Auto-ajuste relido como '{current}'." if ok
                    else f"O Windows ainda reporta '{current}'.")

    # ---------------- TRIM (movido do disco) ----------------
    def trim_compat(core, ctx):
        state = core.delete_notify_state()
        if not state.get("values"):
            return False, "O fsutil não respondeu o estado do TRIM; preservado."
        if state.get("trim_on"):
            return False, "TRIM já está ativo em todos os sistemas de arquivo. Nada a reparar."
        return _needs_admin_to_fix(core,
            "TRIM aparece desligado. Sem ele, o SSD perde desempenho de escrita ao longo do tempo "
            "— e quase sempre é um 'otimizador' anterior que desligou.")

    def trim_apply(core, ctx):
        return core.enable_trim_verified()

    def trim_verify(core, ctx):
        state = core.delete_notify_state()
        ok = bool(state.get("trim_on"))
        return ok, ("fsutil relido: TRIM ativo." if ok else f"TRIM ainda não confirmado: {state.get('raw')}")

    # ---------------- limpeza do pagefile no desligamento ----------------
    MEMORY_MGMT = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"

    def clearpf_compat(core, ctx):
        entry = core.reg_read("HKLM", MEMORY_MGMT, "ClearPageFileAtShutdown")
        if not entry.get("exists") or entry.get("value") == 0:
            return False, "O Windows não está limpando o arquivo de paginação no desligamento. Nada a reparar."
        return _needs_admin_to_fix(core,
            "O Windows está configurado para zerar o arquivo de paginação a cada desligamento. "
            "É uma opção de segurança de ambiente corporativo que virou 'dica de otimização' na "
            "internet: ela não acelera nada e faz o desligamento levar minutos.")

    def clearpf_apply(core, ctx):
        return core.write_registry_values_verified(
            [{"root": "HKLM", "path": MEMORY_MGMT, "name": "ClearPageFileAtShutdown", "value": 0}])

    def clearpf_verify(core, ctx):
        entry = core.reg_read("HKLM", MEMORY_MGMT, "ClearPageFileAtShutdown")
        ok = (not entry.get("exists")) or entry.get("value") == 0
        return ok, ("Relido: o arquivo de paginação não é mais zerado no desligamento." if ok
                    else f"O Windows ainda reporta {entry.get('value')}.")

    # ---------------- cache de escrita do disco ----------------
    def cache_compat(core, ctx):
        state = core.disk_write_cache_state()
        if not state.get("readable"):
            return False, "O estado do cache de escrita não pode ser lido; preservado."
        off = state.get("off") or []
        if not off:
            return False, "O cache de escrita está habilitado em todos os discos. Nada a reparar."
        return _needs_admin_to_fix(core,
            "Cache de escrita DESLIGADO em: " + ", ".join(d["name"] for d in off) + ". "
            "Isso derruba a velocidade de escrita do disco de forma dramática e não protege nada "
            "sozinho - só faz sentido com no-break e por decisão de quem administra o servidor.")

    def cache_apply(core, ctx):
        return core.enable_write_cache_verified()

    def cache_verify(core, ctx):
        state = core.disk_write_cache_state()
        ok = not (state.get("off") or [])
        return ok, ("Cache de escrita relido como habilitado em todos os discos." if ok
                    else "Ainda desligado em: " + ", ".join(d["name"] for d in (state.get("off") or [])))

    # ---------------- Cache de abertura de programas ----------------
    def launch_compat(core, ctx):
        st = core.app_launch_cache_state()
        if not st.get("supported"):
            return False, "Windows only"
        if not st.get("broken"):
            return False, "SysMain e Prefetcher já estão ativos. Nada a reparar."
        # O modo Agressivo desliga os dois de propósito quando o PC só tem SSD.
        # Religar aqui para o item seguinte desligar de novo seria trabalho jogado
        # fora; com HD mecânico no PC o conserto continua valendo.
        if ctx.get("resolved_profile") == "agressivo" and only_solid_state(core):
            return False, ("No modo Agressivo, com só SSD, o SysMain e o Prefetcher ficam "
                           "desligados de propósito. Os modos Máximo e os perfis religam.")
        # A checagem de administrador mora TODA dentro de _needs_admin_to_fix -
        # um `if not core.is_admin()` proprio aqui duplicaria a regra, e o
        # self-test reprova exatamente isso (ele conta as ocorrencias). O
        # diagnostico vem primeiro; a permissao so e pedida quando ha conserto.
        return _needs_admin_to_fix(core, st.get("detail", ""))

    def launch_apply(core, ctx):
        return core.repair_app_launch_cache()

    def launch_verify(core, ctx):
        st = core.app_launch_cache_state(force=True)
        ok = not st.get("broken")
        return ok, ("SysMain ativo e EnablePrefetcher relido em 3."
                    if ok else st.get("detail", "Ainda desligado."))

    return [
        OptimizationTask(
            "system_restore_repair", "Religar a Proteção do Sistema", MODULE["id"],
            "Reparo / Restauração", _ALL_PROFILES, risk="low", reversible=False,
            description="Reativa os pontos de restauração do Windows no disco do sistema. Isto é "
                        "pré-requisito do próprio AZOR: sem Proteção do Sistema, o ponto de "
                        "restauração que ele pede antes de otimizar não pode ser criado.",
            apply=restore_apply, verify=restore_verify, compatible=restore_compat,
            tags=("repair", "restore", "safety"),
            source="Enable-ComputerRestore (módulo Microsoft.PowerShell.Management). O estado é "
                   "lido em HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore "
                   "(RPSessionInterval e DisableSR).",
            trade_off="Os pontos de restauração ocupam espaço em disco — por padrão poucos por cento "
                      "do volume. Não é reversível pelo AZOR: desligar a rede de segurança do "
                      "cliente não é uma função do produto.",
            metric="Existência de ponto de restauração antes de qualquer alteração",
        ),
        OptimizationTask(
            "firewall_repair", "Religar o Firewall do Windows", MODULE["id"],
            "Reparo / Segurança", _ALL_PROFILES, risk="low", reversible=False,
            description="Religa os perfis do firewall que estiverem desligados e confirma por "
                        "releitura. Desligar o firewall é um 'tweak' que circula como se desse FPS; "
                        "ele não dá, e deixa a máquina exposta na rede.",
            apply=firewall_apply, verify=firewall_verify, compatible=firewall_compat,
            tags=("repair", "security", "network"),
            source="Set-NetFirewallProfile -Enabled True (módulo NetSecurity do PowerShell). Os "
                   "perfis são lidos por Get-NetFirewallProfile, cujos nomes de propriedade não "
                   "dependem do idioma do Windows.",
            trade_off="Nenhum custo de desempenho mensurável. Não é reversível pelo AZOR: o app não "
                      "desliga firewall de cliente.",
            metric="",
        ),
        OptimizationTask(
            "write_cache_repair", "Religar o cache de escrita do disco", MODULE["id"],
            "Reparo / Disco", _ALL_PROFILES, risk="medium", reversible=False, restart=True,
            description="Devolve o cache de escrita aos discos em que ele foi desligado. Desligado, "
                        "cada gravação espera o disco confirmar fisicamente - o PC inteiro fica lento "
                        "de um jeito que nenhum tweak compensa.",
            apply=cache_apply, verify=cache_verify, compatible=cache_compat,
            tags=("repair", "disk", "restart"),
            source="UserWriteCacheSetting em ...\\Enum\\<disco>\\Device Parameters\\Disk - e a "
                   "caixa 'Habilitar cache de gravação no dispositivo' da aba Políticas do disco, no "
                   "Gerenciador de Dispositivos.",
            trade_off="Não e reversível pelo AZOR: desligar o cache de escrita de novo só faz sentido "
                      "com no-break e por decisão de quem administra a máquina, não num otimizador de "
                      "jogo. Exige reiniciar.",
            metric="Velocidade de escrita do disco",
        ),
        OptimizationTask(
            "clear_pagefile_repair", "Parar de zerar o arquivo de paginação no desligamento",
            MODULE["id"], "Reparo / Desligamento", _ALL_PROFILES, risk="low", reversible=False,
            description="Desfaz a configuração que faz o Windows sobrescrever o arquivo de paginação "
                        "inteiro toda vez que o PC desliga. Em um pagefile de vários GB isso são "
                        "minutos de tela de desligamento — e nenhuma melhora de desempenho.",
            apply=clearpf_apply, verify=clearpf_verify, compatible=clearpf_compat,
            tags=("repair", "shutdown", "memory"),
            source="ClearPageFileAtShutdown em HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session "
                   "Manager\\Memory Management — opção de segurança documentada pela Microsoft, "
                   "pensada para máquinas com dados sensíveis.",
            trade_off="Não é reversível pelo AZOR: religar isso só faz sentido em ambiente que exige "
                      "apagar dados residuais por política, e nesse caso quem configura é o "
                      "administrador do domínio, não um otimizador de jogo.",
            metric="Tempo de desligamento",
        ),
        OptimizationTask(
            "bcd_timer_repair", "Remover overrides de temporizador no boot", MODULE["id"],
            "Reparo / Boot", _ALL_PROFILES, risk="medium", reversible=False, restart=True,
            description="Apaga do boot as opções useplatformclock, disabledynamictick, tscsyncpolicy "
                        "e similares. Nenhuma delas existe num Windows de fábrica: se está lá, "
                        "alguém gravou. Forçar o HPET como fonte de tempo costuma AUMENTAR a "
                        "latência em CPU moderna, que é o contrário do que o guia prometia.",
            apply=bcd_apply, verify=bcd_verify, compatible=bcd_compat,
            tags=("repair", "boot", "timer", "restart"),
            source="bcdedit /deletevalue {current} <opção> — Opções de inicialização do Windows, "
                   "Microsoft Learn. A detecção é pela presença do nome da opção no {current}, que "
                   "não é traduzido, e não pelo valor, que é.",
            trade_off="Exige reiniciar. Não é reversível pelo AZOR de propósito: o app não oferece "
                      "um botão para forçar o HPET de volta. Se você quiser mesmo, o comando é "
                      "'bcdedit /set useplatformclock true'.",
            metric="Latência de DPC e jitter de agendamento (µs)",
        ),
        OptimizationTask(
            "essential_services_repair", "Religar serviços essenciais desabilitados", MODULE["id"],
            "Reparo / Serviços", _ALL_PROFILES, risk="medium", reversible=False,
            description="Devolve ao padrão do Windows os serviços que nenhum otimizador deveria ter "
                        "desligado: áudio, temas, DHCP, DNS, log de eventos, agendador, firewall e "
                        "Windows Update. Cada um é relido depois de alterado.",
            apply=services_apply, verify=services_verify, compatible=services_compat,
            tags=("repair", "service"),
            source="Tipos de inicialização padrão dos serviços do Windows. Busca e Windows Defender "
                   "ficam FORA desta lista de propósito: desligar a busca é preferência legítima, e "
                   "o Defender fica desligado em PC com antivírus de terceiro.",
            trade_off="Não é reversível pelo AZOR: o app não oferece desligar o áudio ou o firewall "
                      "de novo. O padrão restaurado é o do Windows, não o que estava antes — se o "
                      "serviço já chegou desabilitado, 'o que estava antes' também é o defeito.",
            metric="Funcionalidades do Windows que voltam a funcionar",
        ),
        OptimizationTask(
            "app_launch_cache_repair", "Religar o pre-carregamento de programas", MODULE["id"],
            "Reparo / Desempenho", _ALL_PROFILES, risk="low", reversible=False,
            description="Religa o SysMain (antigo Superfetch) e o Prefetcher, que são as duas pecas "
                        "que fazem o Windows pre-carregar os programas que você mais usa. Quando os "
                        "dois estão desligados, TODO aplicativo passa a abrir do zero, e o cliente "
                        "sente o PC lento sem saber por que.",
            apply=launch_apply, verify=launch_verify, compatible=launch_compat,
            tags=("repair", "memory", "startup"),
            source="Servico SysMain e EnablePrefetcher em HKLM\\SYSTEM\\CurrentControlSet\\Control\\"
                   "Session Manager\\Memory Management\\PrefetchParameters. O valor 3 (padrão do "
                   "Windows) pre-carrega aplicativos e boot.",
            trade_off="\"Desative o Superfetch, você tem SSD\" e conselho de 2012: nasceu quando o "
                      "serviço paginava em disco mecanico e quando SSD tinha pouca resistencia a "
                      "escrita. Em Windows 10/11 ele cacheia em RAM, cede prioridade sob carga e nem "
                      "roda durante a partida - ou seja, desligar não devolve FPS, so devolve tela de "
                      "espera ao abrir programa. Não e reversível pelo AZOR: quem quiser desligar de "
                      "novo tem o item experimental na lista manual.",
            metric="Tempo até a janela do programa aparecer, da segunda abertura em diante",
        ),
        OptimizationTask(
            "tcp_autotuning_repair", "Reparar o auto-ajuste da janela TCP", MODULE["id"],
            "Reparo / Rede", _ALL_PROFILES, risk="low", reversible=False,
            description="Devolve o auto-ajuste da janela de recepção para 'normal'. Vários "
                        "otimizadores desligam esse recurso achando que reduz ping; o efeito real é "
                        "download preso em uma fração da velocidade contratada.",
            apply=autotuning_apply, verify=autotuning_verify, compatible=autotuning_compat,
            tags=("repair", "tcp"),
            source="Set-NetTCPSetting -AutoTuningLevelLocal Normal — Receive Window Auto-Tuning, "
                   "documentado pela Microsoft. 'Normal' é o padrão do Windows desde o Vista.",
            trade_off="Nenhum custo conhecido no Windows atual. Não é reversível pelo AZOR: voltar "
                      "para 'disabled' é justamente o defeito que este item conserta.",
            metric="Vazão de download em conexão rápida",
        ),
        OptimizationTask(
            "trim_repair", "Reativar o TRIM do SSD", MODULE["id"],
            "Reparo / Disco", _ALL_PROFILES, risk="low", reversible=False,
            description="Religa a notificação de exclusão (TRIM) quando ela foi desativada. Só "
                        "aparece se o TRIM estiver realmente desligado neste PC.",
            apply=trim_apply, verify=trim_verify, compatible=trim_compat, tags=("repair", "ssd"),
            source="fsutil behavior set disabledeletenotify 0 — referência do fsutil, Microsoft "
                   "Learn. O nome da chave é invertido: DisableDeleteNotify=0 significa TRIM LIGADO.",
            trade_off="Não é reversível pelo AZOR de propósito. Desligar o TRIM de novo degradaria o "
                      "SSD, e o app não oferece um botão para piorar o disco do cliente.",
            metric="Desempenho de escrita do SSD ao longo do tempo",
        ),
    ]
