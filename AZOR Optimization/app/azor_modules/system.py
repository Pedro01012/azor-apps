"""Nucleo do Windows: agendador, MMCSS, throttling e modo exclusivo.

Este e o modulo que mexe onde o ganho e real e onde o custo tambem e. Tudo aqui
grava em HKLM, entao tudo aqui exige o AZOR aberto como administrador -- e
declara isso em `compatible` em vez de falhar com "acesso negado" na cara do
usuario.

Duas regras que valem para o modulo inteiro:

  * Nada que reduza seguranca entra no lote de um clique. O tweak existe, e
    reversivel e esta documentado, mas quem liga e o usuario, num clique proprio
    (`automatic=False`), depois de ler o custo.
  * Perfil JOGO + LIVE nao e o competitivo com outro nome. Reservar 100% da CPU
    para o jogo estrangula o encoder da live, entao os valores mudam por perfil.
"""
from __future__ import annotations

import os

from .base import OptimizationTask
from .regtweak import RegSpec, V, compile_specs

MODULE = {
    "id": "system",
    "label": "Núcleo do Windows",
    "description": "Agendador, MMCSS, power throttling e modo exclusivo de tela cheia. Tudo verificado por releitura e reversível pelo baseline.",
    "automatic": True,
}

MULTIMEDIA = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
GAMES_TASK = MULTIMEDIA + r"\Tasks\Games"
GAME_STORE = r"System\GameConfigStore"
DEVICE_GUARD = r"SYSTEM\CurrentControlSet\Control\DeviceGuard"
HVCI = DEVICE_GUARD + r"\Scenarios\HypervisorEnforcedCodeIntegrity"


def _needs_admin(core, ctx):
    if not core.is_admin():
        return False, ("Este ajuste grava em HKLM e exige o AZOR aberto como administrador. "
                       "Feche e reabra pelo atalho do AZOR para liberá-lo.")
    return True, "Privilégio de administrador confirmado."


def _needs_admin_and_desktop(core, ctx):
    ok, detail = _needs_admin(core, ctx)
    if not ok:
        return ok, detail
    if ctx.get("hardware", {}).get("battery"):
        return True, ("Notebook detectado: o ajuste vale, mas custa autonomia. Ele continua reversível "
                      "com um clique quando você sair da tomada.")
    return True, detail


# Perfil JOGO + LIVE precisa de folga para o encoder; competitivo nao.
def _responsiveness_values(ctx):
    # Quem faz live marca "Faço live" nos Ajustes: o encoder precisa da reserva padrão.
    stream = str(ctx.get("resolved_profile") or "") == "stream" or bool(ctx.get("streamer"))
    return [V("HKLM", MULTIMEDIA, "SystemResponsiveness", 20 if stream else 10)]


SPECS = [
    RegSpec(
        id="system_responsiveness",
        name="Reserva de CPU do MMCSS",
        category="Núcleo / Agendador",
        profiles=("competitive", "campanha", "stream"),
        risk="medium",
        values=[V("HKLM", MULTIMEDIA, "SystemResponsiveness", 10)],
        values_for=_responsiveness_values,
        compatible=_needs_admin,
        description="Teste manual da reserva MMCSS: 10 no competitivo e 20 em transmissão. "
                    "Valores menores que 10 são tratados como 20 pelo Windows. Não garante ganho de FPS.",
        source="Multimedia Class Scheduler Service (MMCSS) - Microsoft Learn. Chave SystemResponsiveness "
               "em HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile. "
               "O padrão do Windows cliente é 20 (20% reservados ao que não é multimídia).",
        trade_off="Áudio e vídeo de segundo plano (Discord, navegador, captura) ficam com menos CPU "
                  "garantida sob carga total. Se você grava ou transmite, use o perfil JOGO + LIVE.",
        metric="1% low e p99 de frametime",
        tags=("mmcss", "scheduler"),
    ),
    RegSpec(
        id="network_throttling_off",
        name="Desligar o limitador de rede do MMCSS",
        category="Núcleo / Rede",
        profiles=("competitive", "campanha", "stream"),
        risk="medium",
        values=[V("HKLM", MULTIMEDIA, "NetworkThrottlingIndex", 0xFFFFFFFF)],
        compatible=_needs_admin,
        description="O Windows limita a 10 pacotes por milissegundo enquanto há multimídia ativa. "
                    "0xFFFFFFFF desliga esse limitador, que é o valor que a própria Microsoft documenta "
                    "para desabilitá-lo.",
        source="Multimedia Class Scheduler Service - NetworkThrottlingIndex, mesma chave SystemProfile. "
               "Padrão 10; 0xFFFFFFFF significa 'sem limitação'.",
        trade_off="O limitador existe para a reprodução de mídia não engasgar quando a rede satura. "
                  "Sem ele, em rede muito carregada, vídeo pode gaguejar. Em jogo online, o efeito "
                  "esperado e o contrário: menos atraso na fila de pacotes.",
        metric="Jitter de rede em jogo",
        tags=("mmcss", "network"),
    ),
    RegSpec(
        id="mmcss_games_priority",
        name="Perfil MMCSS de Jogos em prioridade alta",
        category="Núcleo / Agendador",
        profiles=("competitive", "campanha"),
        risk="medium",
        values=[
            V("HKLM", GAMES_TASK, "GPU Priority", 8),
            V("HKLM", GAMES_TASK, "Priority", 6),
            V("HKLM", GAMES_TASK, "Scheduling Category", "High"),
            V("HKLM", GAMES_TASK, "SFIO Priority", "High"),
            # As duas que faltavam para o perfil ficar completo: sem "Latency
            # Sensitive", o MMCSS nao trata a tarefa como sensivel a atraso, e a
            # categoria alta sozinha rende menos do que parece.
            V("HKLM", GAMES_TASK, "Latency Sensitive", "True"),
            V("HKLM", GAMES_TASK, "Background Only", "False"),
        ],
        compatible=_needs_admin,
        description="Escreve o perfil MMCSS de jogos inteiro: categoria de Medium para High, "
                    "prioridade de 2 para 6, E/S de arquivo em High, tarefa marcada como sensível a "
                    "atraso e fora do modo de segundo plano. Vale para qualquer jogo que se registre no "
                    "MMCSS, que é a maioria dos motores atuais.",
        source="MMCSS Task registry (HKLM\\...\\Multimedia\\SystemProfile\\Tasks\\Games) - Microsoft Learn. "
               "Padrões do Windows: Priority 2, Scheduling Category Medium, SFIO Priority Normal.",
        trade_off="Fica fora do perfil JOGO + LIVE de propósito: com o jogo em categoria High, o "
                  "software de captura disputa CPU em desvantagem e a live é que engasga.",
        metric="1% low e consistência de frametime",
        tags=("mmcss", "scheduler"),
        relations=[{"kind": "combina", "id": "system_responsiveness",
                    "note": "Um reserva CPU para o jogo, o outro coloca a tarefa de jogo em categoria "
                            "alta. Aplicados juntos é que o MMCSS muda de comportamento de verdade."}],
    ),
    RegSpec(
        id="power_throttling_off",
        name="Desligar o Power Throttling",
        category="Núcleo / Energia",
        profiles=("competitive", "stream"),
        risk="medium",
        values=[V("HKLM", r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff", 1)],
        compatible=_needs_admin_and_desktop,
        description="Impede o Windows de jogar threads em estado de eficiência (EcoQoS) por conta própria. "
                    "Complementa o plano AZOR FPS BOOST: um cuida da política de energia, o outro do "
                    "rebaixamento por thread.",
        source="Power Throttling / EcoQoS - Microsoft Learn. Chave PowerThrottlingOff em "
               "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling.",
        trade_off="Consumo e temperatura sobem, e em notebook a autonomia cai de forma perceptível. "
                  "Em desktop na tomada, o custo é ventoinha mais audível.",
        metric="Clock sustentado sob carga",
        tags=("power", "scheduler"),
    ),
    RegSpec(
        id="gamedvr_machine_policy",
        name="Bloquear a gravação em segundo plano no nível da máquina",
        category="Núcleo / Jogos",
        profiles=("competitive",),
        risk="low",
        values=[V("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0)],
        compatible=_needs_admin,
        description="A versão por máquina do mesmo desligamento que já existe por usuário. Ela sobrevive "
                    "a criação de um perfil novo e a reativação pela Game Bar.",
        source="Política AllowGameDVR (Configuração do Computador > Modelos Administrativos > "
               "Componentes do Windows > Gravação e transmissao de jogos do Windows).",
        trade_off="Enquanto estiver aplicado, nenhum usuário deste PC consegue ligar a gravação "
                  "em segundo plano pela Game Bar - inclusive você.",
        metric="FPS medio e 1% low",
        tags=("gaming", "policy"),
    ),
    RegSpec(
        id="fullscreen_exclusive",
        # SAIU DO LOTE AUTOMATICO: existe agora a versao por executavel.
        #
        # Esta chave (GameConfigStore) vale para TODOS os aplicativos do PC.
        # O ganho de latencia acontece dentro do jogo, mas o preco - overlay do
        # Discord, do OBS e dos capturadores parando de aparecer - e cobrado no
        # sistema inteiro, inclusive fora de qualquer partida.
        #
        # `fortnite_fullscreen_exclusive` faz a mesma coisa gravando so no
        # executavel do Fortnite, via AppCompatFlags\\Layers - a mesma chave da
        # caixinha "Desabilitar otimizacoes de tela cheia" nas Propriedades do
        # arquivo. Mesmo beneficio na partida, nenhum efeito fora dela.
        #
        # A versao global continua disponivel manualmente para quem quiser o
        # comportamento antigo em todos os jogos de uma vez.
        automatic=False,
        name="Tela cheia exclusiva (desligar Fullscreen Optimizations)",
        category="Núcleo / Jogos",
        profiles=("competitive",),
        risk="medium",
        values=[
            V("HKCU", GAME_STORE, "GameDVR_FSEBehaviorMode", 2),
            V("HKCU", GAME_STORE, "GameDVR_FSEBehavior", 2),
            V("HKCU", GAME_STORE, "GameDVR_HonorUserFSEBehaviorMode", 1),
            V("HKCU", GAME_STORE, "GameDVR_DXGIHonorFSEWindowsCompatible", 1),
        ],
        description="Devolve ao jogo a tela cheia exclusiva de verdade, em vez da janela sem borda que o "
                    "Windows passou a usar por padrão. É o caminho mais curto entre o frame pronto e o "
                    "monitor, porque tira o compositor do meio.",
        source="Fullscreen Optimizations (HKCU\\System\\GameConfigStore). Mesmas chaves que a aba "
               "Compatibilidade do executável altera ao marcar 'Desabilitar otimizações de tela cheia'.",
        trade_off="Alt-tab fica mais lento, e overlays que desenham por cima (Game Bar, Discord, alguns "
                  "capturadores) podem parar de aparecer. Por isso ele fica fora do perfil JOGO + LIVE.",
        metric="Latência de clique até pixel",
        tags=("gaming", "display"),
    ),
    RegSpec(
        id="menu_show_delay",
        name="Resposta imediata dos menus do Windows",
        category="Núcleo / Interface",
        profiles=("competitive", "stream"),
        risk="low",
        values=[V("HKCU", r"Control Panel\Desktop", "MenuShowDelay", "0")],
        description="Zera o atraso de abertura de menu do shell. Muda a sensação do Windows, não o jogo.",
        source="HKCU\\Control Panel\\Desktop\\MenuShowDelay. Padrão do Windows: 400 ms.",
        trade_off="Menus abrem no instante em que o ponteiro passa, o que algumas pessoas acham "
                  "apressado demais ao navegar pelo teclado.",
        metric="",
        tags=("ui",),
    ),
    RegSpec(
        id="global_timer_resolution",
        name="Fazer o timer de alta resolução valer para todo o sistema",
        category="Núcleo / Timer",
        profiles=("competitive", "campanha", "stream"),
        risk="medium",
        restart=True,
        values=[V("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\Kernel",
                  "GlobalTimerResolutionRequests", 1)],
        compatible=_needs_admin,
        description="Desde o Windows 10 2004, o pedido de timer de 0,5 ms vale só para o processo que "
                    "pediu — o resto do sistema continua no timer grosso. Está chave devolve o "
                    "comportamento global. É o ajuste que faz o Timer do AZOR realmente alcançar o jogo "
                    "em vez de valer só dentro do próprio app.",
        source="Mudança de comportamento do timer em Windows 10 2004, documentada pela Microsoft no "
               "blog de desenvolvimento do kernel; chave GlobalTimerResolutionRequests em "
               "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Kernel.",
        trade_off="Timer fino para o sistema inteiro significa mais interrupções e um pouco mais de "
                  "consumo em repouso — em notebook na bateria isso aparece na autonomia. Exige "
                  "reiniciar para valer.",
        metric="Jitter de agendamento (µs) medido no AZOR Scope",
        tags=("timer", "latency", "restart"),
        relations=[{"kind": "amplia", "id": "latency_timer",
                    "note": "Sem está chave, o pedido de 0,5 ms do Timer do AZOR vale só dentro do "
                            "próprio app e quase não alcança o jogo. Os dois juntos são o ajuste; "
                            "separados, é meio ajuste."}],
    ),
    RegSpec(
        id="kernel_no_paging",
        name="Manter o núcleo do Windows na memória",
        category="RAM / Kernel",
        profiles=("competitive",),
        risk="medium",
        restart=True,
        values=[V("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
                  "DisablePagingExecutive", 1)],
        compatible=lambda core, ctx: (
            (False, "Este ajuste grava em HKLM e exige o AZOR aberto como administrador.")
            if not core.is_admin() else
            (False, f"Com {ctx.get('hardware', {}).get('ram_gb')} GB de RAM, prender o núcleo na "
                    "memória tira espaço de quem precisa mais: o jogo. O AZOR só oferece a partir "
                    "de 16 GB.")
            if float(ctx.get("hardware", {}).get("ram_gb") or 0) < 16 else
            (True, f"{ctx.get('hardware', {}).get('ram_gb')} GB de RAM: há folga para manter o "
                   "núcleo residente.")),
        description="Impede que o Windows mande partes do próprio núcleo e dos drivers para o arquivo "
                    "de paginação. Quando isso acontece durante o jogo, o retorno do disco aparece "
                    "como travada isolada — o tipo que não some por baixar a qualidade gráfica.",
        source="DisablePagingExecutive em HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session "
               "Manager\\Memory Management — referência de registro do gerenciador de memória, "
               "Microsoft Learn.",
        trade_off="O núcleo passa a ocupar RAM permanentemente. Por isso o AZOR só oferece com 16 GB "
                  "ou mais: abaixo disso, a memória é mais útil no jogo. Exige reiniciar.",
        metric="p99 de frametime e travadas isoladas",
        tags=("memory", "kernel", "restart"),
    ),
    RegSpec(
        id="fast_startup_off",
        name="Desligar a Inicialização Rápida",
        category="Núcleo / Boot",
        profiles=("competitive", "campanha", "stream"),
        risk="medium",
        values=[V("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled", 0)],
        compatible=_needs_admin,
        description="A Inicialização Rápida não desliga o PC de verdade: ela hiberna o núcleo do "
                    "Windows e o restaura no próximo boot. É por isso que 'reiniciei e voltou tudo' "
                    "acontece — ajuste de driver e de kernel volta com o estado antigo junto. "
                    "Desligada, o desligamento passa a ser um desligamento.",
        source="HiberbootEnabled em HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power. "
               "É a mesma caixa de Opções de Energia > Escolher a função dos botões de energia > "
               "Ligar inicialização rápida. O AZOR usa a chave em vez de 'powercfg /h off' para não "
               "apagar o arquivo de hibernação de quem usa hibernar.",
        trade_off="O PC liga alguns segundos mais devagar depois de um desligamento. Em compensação, "
                  "reiniciar passa a valer de verdade: driver novo, ajuste de kernel e mudança de BIOS "
                  "só assumem depois de um boot completo.",
        metric="Consistência dos ajustes entre reinícios",
        tags=("boot", "persistence"),
    ),
    RegSpec(
        id="svchost_split_threshold",
        name="Agrupar os serviços do Windows em menos processos",
        # SAIU DO LOTE AUTOMATICO na auditoria.
        #
        # O que ele entrega: menos linhas no Gerenciador de Tarefas e alguma RAM
        # em repouso. O que ele NAO entrega: um quadro por segundo, um
        # milissegundo de frametime ou de input lag - nada da lista do que o
        # cliente quer.
        #
        # O que ele cobra: a Microsoft separou os servicos em processos
        # proprios acima de 3,5 GB de RAM DE PROPOSITO, para que a falha de um
        # servico nao derrube os vizinhos. Juntar tudo de volta troca
        # estabilidade por cosmetica - e estabilidade e a prioridade numero 1.
        #
        # Continua disponivel para quem escolher item a item, com o aviso.
        automatic=False,
        category="Núcleo / Serviços",
        profiles=("competitive",),
        risk="medium",
        values=[V("HKLM", r"SYSTEM\CurrentControlSet\Control", "SvcHostSplitThresholdInKB", 0x4000000)],
        compatible=_needs_admin,
        description="Em PC com 4 GB ou mais, o Windows separa cada serviço em seu próprio svchost.exe "
                    "— daí a lista enorme de processos idênticos no Gerenciador de Tarefas. Elevando o "
                    "limiar, eles voltam a compartilhar processo: menos processos, menos memória de "
                    "estrutura e menos trocas de contexto.",
        source="SvcHostSplitThresholdInKB em HKLM\\SYSTEM\\CurrentControlSet\\Control — o mesmo "
               "limiar que a Microsoft documenta para o agrupamento de serviços por quantidade de RAM.",
        trade_off="Serviços agrupados compartilham processo: se um falha, pode derrubar os outros do "
                  "mesmo grupo, e o Gerenciador de Tarefas deixa de mostrar qual serviço consome o quê. "
                  "Vale a pena em PC de jogo, menos em máquina de trabalho onde o diagnóstico importa. "
                  "Só passa a valer depois de reiniciar.",
        metric="Número de processos e memória em repouso",
        restart=True,
        tags=("services", "memory"),
    ),
    RegSpec(
        id="delivery_optimization_off",
        name="Parar de enviar atualizações do Windows para outros PCs",
        category="Núcleo / Rede",
        profiles=("competitive", "stream"),
        risk="low",
        values=[V("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", 0)],
        compatible=_needs_admin,
        description="A Otimização de Entrega usa a sua conexão para distribuir atualizações do Windows "
                    "a outros computadores, inclusive fora da sua rede. É upload consumido em segundo "
                    "plano, e upload saturado é uma das causas reais de ping instável em jogo.",
        source="Política DODownloadMode (Configuração do Computador > Componentes do Windows > "
               "Otimização de Entrega). 0 = somente HTTP, sem compartilhamento com outros pares.",
        trade_off="Baixar atualizações grandes pode ficar mais lento em rede com vários PCs, porque "
                  "cada um passa a buscar direto da Microsoft em vez de pegar do vizinho. As "
                  "atualizações continuam chegando normalmente.",
        metric="Upload em segundo plano e estabilidade do ping",
        tags=("network", "policy", "background"),
    ),
    RegSpec(
        id="telemetry_policy_min",
        name="Telemetria do Windows no mínimo permitido",
        category="Núcleo / Privacidade",
        profiles=("competitive", "stream"),
        risk="low",
        values=[V("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0)],
        compatible=_needs_admin,
        description="Grava a política de coleta de dados no menor nível. Complementa o desligamento "
                    "do serviço DiagTrack: um tira o coletor de execução, o outro diz ao Windows "
                    "para não coletar.",
        source="Política AllowTelemetry (Configuração do Computador > Modelos Administrativos > "
               "Componentes do Windows > Coleta de Dados e Versões Prévias) — Microsoft Learn.",
        trade_off="Nas edições Home e Pro o Windows trata 0 como 1 (Básico): a política existe, mas "
                  "só as edições Enterprise/Education honram o zero. O AZOR grava e relê o valor, e "
                  "não promete mais do que isso.",
        metric="Uso de rede e disco em repouso",
        tags=("privacy", "telemetry", "policy"),
        relations=[{"kind": "combina", "id": "diagtrack_off",
                    "note": "Este diz ao Windows para não coletar; o outro tira o coletor de "
                            "execução. Sozinho, cada um é metade do caminho."}],
    ),
    RegSpec(
        id="win32_priority_separation",
        name="Quantum do agendador para primeiro plano",
        category="Núcleo / Agendador",
        profiles=("competitive",),
        risk="experimental",
        automatic=False,
        values=[V("HKLM", r"SYSTEM\CurrentControlSet\Control\PriorityControl", "Win32PrioritySeparation", 0x26)],
        compatible=_needs_admin,
        description="Muda o tamanho e o tipo do quantum do agendador (0x26: quantum longo, variável, "
                    "impulso 2:1 para o primeiro plano). Fica FORA do lote automático de propósito: o "
                    "resultado depende do jogo e do número de núcleos, então ele só vale como teste A/B "
                    "seu, com FPS medido antes e depois.",
        source="Win32PrioritySeparation (HKLM\\SYSTEM\\CurrentControlSet\\Control\\PriorityControl), "
               "descrito em Windows Internals: bits 4-5 tamanho do quantum, 2-3 fixo/variável, 0-1 "
               "impulso do primeiro plano. Padrão do Windows cliente: 2.",
        trade_off="Este é o único item da lista que o AZOR não afirma que melhora. Em parte das máquinas "
                  "ele não muda nada mensurável, e em jogo que usa muitas threads pode piorar o 1% low. "
                  "Aplique, meca, e reverta se não melhorar.",
        metric="1% low medido antes e depois",
        tags=("scheduler", "ab-test"),
    ),
    RegSpec(
        id="memory_integrity_off",
        name="Desligar a Integridade de Memória (HVCI/VBS)",
        category="Núcleo / Segurança",
        profiles=("competitive",),
        risk="high",
        automatic=False,
        restart=True,
        restart_note="Só passa a valer depois de reiniciar. Confira em Segurança do Windows > "
                     "Segurança do dispositivo > Isolamento do núcleo.",
        values=[
            V("HKLM", DEVICE_GUARD, "EnableVirtualizationBasedSecurity", 0),
            V("HKLM", HVCI, "Enabled", 0),
        ],
        compatible=_needs_admin,
        description="A Integridade de Memória roda o kernel dentro de um hipervisor. Isso custa "
                    "desempenho de CPU em toda chamada de sistema, e e o maior item isolado desta lista "
                    "num Windows 11 de fábrica. Desligar devolve esse custo -- e a proteção junto.",
        source="Virtualization-based Security / Memory Integrity (HVCI) - Microsoft Learn. O mesmo "
               "interruptor de Segurança do Windows > Segurança do dispositivo > Isolamento do núcleo.",
        trade_off="VOCE FICA MENOS PROTEGIDO. A Integridade de Memória é o que impede um driver "
                  "malicioso assinado de rodar código no kernel. Alem disso, alguns anticheats exigem "
                  "que ela esteja ligada e vao recusar iniciar o jogo. Por isso este item nunca entra "
                  "no lote de um clique: ele exige um clique seu, e volta com outro.",
        metric="FPS medio e 1% low em jogo limitado por CPU",
        tags=("security", "cpu", "manual"),
    ),
]

TASKS, KEYS = compile_specs(MODULE["id"], SPECS)


def _priority_task():
    """Motor de sessão, como o Timer: existe enquanto o AZOR estiver aberto.

    Não escreve nada no Windows — prioridade de processo morre junto com o
    processo. Por isso é reversível por natureza e não entra no baseline.
    """
    def compat(core, ctx):
        if os.name != "nt":
            return False, "Windows only"
        games = core.load_settings().get("configured_games") or []
        if not games:
            return False, "Nenhum jogo configurado para o AZOR acompanhar."
        return True, ("O AZOR sobe o jogo para prioridade Alta assim que ele abrir. "
                      f"Acompanhando: {', '.join(str(g) for g in games[:3])}.")

    def verify(core, ctx):
        st = core.GAME_PRIORITY.status()
        ok = bool(st.get("running"))
        return ok, ("Motor de prioridade em execução nesta sessão." if ok
                    else "O motor de prioridade não está em execução.")

    def revert(core, ctx):
        ok, detail = core.GAME_PRIORITY.stop()
        st = core.load_settings()
        st["game_priority_engine"] = False
        core.save_settings(st)
        return ok, detail

    return [OptimizationTask(
        "game_priority_engine", "Prioridade Alta para o jogo em execução", MODULE["id"],
        "Núcleo / Agendador", ("competitive", "campanha", "stream"), risk="low",
        description="Enquanto o jogo estiver aberto, o AZOR eleva o processo dele para prioridade "
                    "Alta. O Modo de Jogo do Windows reduz interrupções, mas não mexe na prioridade "
                    "— e prioridade é o que decide quem roda primeiro quando falta núcleo, que é "
                    "exatamente o momento em que o 1% low despenca.",
        apply=lambda c, x: c.GAME_PRIORITY.start(), verify=verify, revert=revert, compatible=compat,
        tags=("scheduler", "session", "latency", "cpu"),
        source="SetPriorityClass (kernel32) com HIGH_PRIORITY_CLASS — a mesma prioridade que o "
               "Gerenciador de Tarefas oferece em Detalhes > Definir prioridade > Alta.",
        trade_off="Vale só enquanto o AZOR estiver aberto: prioridade de processo morre com o "
                  "processo, e por isso este item não escreve nada no Windows. O AZOR usa Alta e "
                  "nunca Tempo Real — em tempo real o jogo passa na frente do próprio driver de "
                  "entrada e do áudio, e o PC inteiro engasga. Nada de segundo plano é rebaixado: "
                  "derrubar processo que o app não conhece quebra navegador e captura sem ninguém "
                  "entender por quê.",
        metric="1% low e consistência de frametime sob falta de núcleo",
        relations=[{"kind": "combina", "id": "mmcss_games_priority",
                    "note": "Um sobe a prioridade do processo, o outro sobe a categoria da tarefa no "
                            "MMCSS. São camadas diferentes do mesmo agendador."}],
    )]


def _hibernate_task():
    def compat(core, ctx):
        if ctx.get("hardware", {}).get("battery"):
            return False, ("Notebook detectado. Hibernar e útil em notebook, e desligar isso tira um "
                           "recurso que você provavelmente usa. O AZOR não oferece aqui.")
        state = core.hibernate_state()
        if not state.get("enabled"):
            return False, "A hibernação já está desligada neste PC."
        size = state.get("file_gb")
        found = ("Hibernação ligada" + (f", com {size} GB ocupados pelo hiberfil.sys." if size else "."))
        if not core.is_admin():
            return False, found + " Desligar exige o AZOR aberto como administrador."
        return True, found

    def verify(core, ctx):
        state = core.hibernate_state(force=True)
        ok = not state.get("enabled")
        return ok, ("powercfg relido: hibernação desligada." if ok
                    else "O Windows ainda reporta hibernação ativa.")

    def revert(core, ctx):
        return core.set_hibernate_verified(True)

    return [OptimizationTask(
        "hibernate_off", "Desligar a hibernação", MODULE["id"], "Núcleo / Boot",
        ("competitive",), risk="medium",
        description="Libera o hiberfil.sys, que ocupa perto de 40% da RAM em disco, e fecha de vez a "
                    "porta da Inicialização Rápida - ela depende da hibernação para existir. E o "
                    "complemento do ajuste que desliga a Inicialização Rápida: um tira o "
                    "comportamento, este tira a base.",
        apply=lambda c, x: c.set_hibernate_verified(False), verify=verify, revert=revert,
        compatible=compat, tags=("boot", "disk", "persistence"),
        source="powercfg /hibernate off - opções de linha de comando do powercfg, Microsoft Learn.",
        trade_off="Você perde hibernar e a Inicialização Rápida. Em desktop, nenhum dos dois costuma "
                  "fazer falta; em notebook, hibernar faz, e por isso o AZOR nem oferece la.",
        metric="Espaco livre no disco do sistema e consistência entre reinicios",
        relations=[{"kind": "combina", "id": "fast_startup_off",
                    "note": "A Inicialização Rápida usa a hibernação. Desligar só ela deixa a base "
                            "no lugar; desligar as duas fecha o assunto."}],
    )]


def _defender_tasks():
    """Exclusão de pasta de jogo no Defender.

    Não é um RegSpec porque exclusão do Defender não é chave de registro: é estado
    do próprio antivírus, lido e escrito por Get/Add/Remove-MpPreference.
    """
    def compat(core, ctx):
        st = core.defender_status()
        if not st.get("readable"):
            return False, "O estado do Defender não pôde ser lido; preservado."
        if not st.get("active"):
            return False, (f"O Defender está em modo {st.get('mode') or 'passivo'} — há outro "
                           "antivírus no comando. Excluir pasta aqui não mudaria nada, então o AZOR "
                           "não finge que muda. Faça a exclusão no antivírus que está ativo.")
        folders = core.game_folders()
        if not folders:
            return False, "Nenhuma pasta de jogo foi localizada nos lançadores instalados."
        have = {str(x).lower() for x in (st.get("exclusions") or [])}
        missing = [f for f in folders if f.lower() not in have]
        if not missing:
            return False, "As pastas de jogo encontradas já estão excluídas do Defender."
        found = f"{len(missing)} pasta(s) de jogo ainda verificadas em tempo real: " + ", ".join(missing[:2]) + "."
        if not core.is_admin():
            return False, found + " Alterar exclusões exige o AZOR aberto como administrador."
        return True, found

    def apply(core, ctx):
        st = core.defender_status()
        have = {str(x).lower() for x in (st.get("exclusions") or [])}
        return core.set_defender_exclusions_verified(
            [f for f in core.game_folders() if f.lower() not in have], add=True)

    def verify(core, ctx):
        st = core.defender_status(force=True)
        have = {str(x).lower() for x in (st.get("exclusions") or [])}
        missing = [f for f in core.game_folders() if f.lower() not in have]
        ok = not missing
        return ok, ("Get-MpPreference relido: as pastas de jogo estão excluídas." if ok
                    else "Ainda sem exclusão: " + ", ".join(missing[:3]))

    def revert(core, ctx):
        original = core.baseline_state().get("defender_exclusions")
        if not isinstance(original, list):
            return False, "O baseline não registrou as exclusões anteriores do Defender."
        have = {str(x).lower() for x in original}
        extra = [f for f in core.game_folders() if f.lower() not in have]
        if not extra:
            return True, "Nenhuma exclusão adicionada pelo AZOR para remover."
        return core.set_defender_exclusions_verified(extra, add=False)

    return [OptimizationTask(
        "defender_game_exclusions", "Tirar as pastas de jogo da verificação em tempo real",
        MODULE["id"], "Núcleo / Segurança", ("competitive",), risk="medium", automatic=False,
        description="Cada arquivo que o jogo lê passa antes pelo antivírus. Em carregamento de mapa "
                    "e compilação de shader, isso são milhares de verificações por segundo. Excluir "
                    "apenas as pastas de instalação dos jogos detectados tira esse custo de onde ele "
                    "mais aparece.",
        apply=apply, verify=verify, revert=revert, compatible=compat,
        tags=("security", "disk", "manual"),
        source="Add-MpPreference -ExclusionPath / Get-MpPreference — módulo Defender do PowerShell, "
               "documentado pela Microsoft. É a mesma lista de Segurança do Windows > Proteção contra "
               "vírus > Exclusões.",
        trade_off="O que estiver dentro dessas pastas deixa de ser verificado em tempo real — "
                  "inclusive um módulo ou 'cheat' baixado para dentro da pasta do jogo. Por isso o "
                  "AZOR exclui só as pastas de instalação que ele mesmo detectou, nunca o disco "
                  "inteiro nem Downloads, e por isso este item exige um clique seu.",
        metric="Tempo de carregamento e picos de I/O durante a partida",
        relations=[{"kind": "cuidado", "id": "diagtrack_off",
                    "note": "São coisas diferentes: um reduz telemetria, o outro reduz verificação "
                            "de vírus. Aplicar os dois não soma risco, mas só o segundo mexe em "
                            "proteção."}],
    )]


def tasks():
    return list(TASKS) + _priority_task() + _hibernate_task() + _defender_tasks()
