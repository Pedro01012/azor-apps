"""Evidence-aware selection. A writable setting is not proof of a gaming gain."""
from dataclasses import replace

# Preserved as explicit advanced choices; never silently applied by a profile.
MANUAL = {
    'system_responsiveness': 'MMCSS é dependente da carga; valores menores que 10 não eliminam a reserva. Exige comparação real.',
    'mmcss_games_priority': 'GPU Priority e SFIO Priority não são usados pelo MMCSS. Não aplicar como ganho de FPS.',
    'network_throttling_off': 'Comportamento depende da carga multimídia/rede; não é otimização universal de ping.',
    'global_timer_resolution': 'Timer global não deve ser forçado por um clique; escopo e efeito variam por versão/processo.',
    'latency_timer': 'Timer só deve ser solicitado quando necessário e não comprova latência de entrada do jogo.',
    'azor_memory_engine': 'Esvaziar memória não é ganho de desempenho. Motor fica sob controle explícito.',
    'game_priority_engine': 'Prioridade exige teste por jogo e restauração da classe original.',
    'kernel_no_paging': 'Não há benefício universal comprovado para esta máquina; preservar gerenciamento do Windows.',
    'power_throttling_off': 'Desligar economia globalmente aumenta consumo; preservar sem medição da carga.',
    'hags': 'Compatibilidade do driver não comprova ganho. Testar no jogo antes de escolher.',
    'gpu_interrupt_priority': 'Alterar política de interrupções requer validação específica do driver/hardware.',
    'nagle_off': 'Ajuste de TCP não otimiza automaticamente tráfego UDP de jogos.',
    'nic_interrupt_moderation_off': 'Menos coalescência aumenta interrupções e pode elevar CPU. Teste específico necessário.',
    'nic_rss_on': 'Exige capacidades do adaptador e backup completo da configuração anterior.',
    'nic_green_ethernet_off': 'Mudança do adaptador pode interromper a conexão. Escolha explícita após medir.',
    'nic_power_saving_off': 'Economia do adaptador depende do uso, de Wi-Fi e bateria. Escolha explícita.',
    'usb_hub_power_off': 'Política de cada dispositivo depende do driver. Exige snapshot por dispositivo.',
    'usb_suspend_off': 'Política USB é uma escolha com custo de energia, não benefício universal de input lag.',
    'display_max_refresh': 'Troca de modo pode apagar a tela. Deve exigir confirmação com reversão temporizada.',
    'fortnite_fullscreen_exclusive': 'Tela cheia depende do jogo/driver. Não impor fora do módulo do jogo.',
    'fortnite_gpu': 'Evitar repetir o mesmo executável no ajuste global e no módulo Fortnite.',
    'all_games_gpu': 'Preferência exige múltiplas GPUs e snapshot dos executáveis exatos.',
    'vrr_windowed': 'Depende de monitor, driver e configuração do jogo; não inferir suporte de uma chave gravável.',
    'nvme_idle_never': 'Não forçar NVMe permanentemente ativo sem evidência de problema.',
    'hibernate_off': 'Hibernação é funcionalidade do usuário; não desativar automaticamente.',
    'fast_startup_off': 'Preferência de inicialização, não aumento de FPS.',
    'startup_delay_off': 'Pode piorar contenção no login; não confundir atraso menor com inicialização mais leve.',
    'keyboard_repeat_fast': 'Repetição de texto não reduz latência física do teclado.',
    'mouse_acceleration_off': 'Afeta o ponteiro do desktop; muitos jogos usam entrada bruta. Preferência pessoal.',
    'visual_effects': 'Uma chave de preset não comprova todos os efeitos alterados. Preservar suavização de fontes.',
    'ntfs_short_names_off': 'Pode afetar compatibilidade de programas antigos; não aplicar genericamente.',
    'ntfs_last_access_off': 'Preservar política do sistema sem carga de I/O que justifique alteração.',
    'diagtrack_off': 'Privacidade é separada de desempenho. Não presumir que o recurso não é utilizado.',
    'spooler_off': 'Ausência de impressora física não elimina impressão PDF e dependências. Escolha explícita.',
    'telemetry_policy_min': 'Políticas variam por edição. Privacidade não é promessa de FPS.',
    'usb_interrupts_ecores': 'Só para controle ou mouse em polling alto (4K/8K) numa CPU híbrida. Exige reiniciar: aplique, jogue e meça de novo na tela do controle.',
}
SAFE = frozenset(('game_mode','automatic_pagefile'))
COMPETITIVE = SAFE | frozenset(('game_dvr','power_plan','background_apps'))
ULTRA = COMPETITIVE | frozenset(('transparency','widgets','search_highlights_off','windows_suggestions','delivery_optimization_off'))

# ---------------------------------------------------------------------------
# Modos da tela inicial
#
# MÁXIMO (recomendado): tudo que tem efeito real e releitura, com rollback exato
# pela transação ou pela reversão apoiada no baseline gravado antes do lote.
# Inclui o que antes ficava como escolha manual. Vale também na bateria: foi
# decisão explícita do produto trocar autonomia por desempenho.
#
# AGRESSIVO: o Máximo mais os ajustes que a auditoria tirou do lote por custo de
# estabilidade, calor ou compatibilidade. Continuam com releitura e reversão, e
# os próprios `compatible` seguem barrando o que não faz sentido no hardware
# (spooler só sem impressora, compressão de memória só com RAM de sobra).
#
# Fora dos dois, sempre: o que reduz proteção (Integridade de Memória, exclusões
# do Defender) e MSI forçado, que pode deixar o PC sem vídeo, sem teclado e mouse
# ou sem boot antes que qualquer reversão consiga rodar.
#
# Também fora dos dois (AB_TEST_ONLY): o que a própria auditoria classifica como
# placebo, cosmético ou teste A/B - quantum do agendador, CPU sem repouso, MPO,
# TdrDelay, agrupamento de svchost, prioridade MMCSS, SysMain e Prefetcher
# desligados. O contrato do servidor já proibia vários no clique único; a versão
# anterior do Agressivo passava por cima porque decide pela política, não pelo
# campo `automatic`. Medido num i5-13400F rodando Fortnite: com a CPU sem repouso
# os núcleos P ficam presos no turbo de todos os núcleos (4,08 GHz) enquanto a
# thread que limita o jogo fica saturada. Continuam a um clique, para medir.
# ---------------------------------------------------------------------------
MAXIMO = ULTRA | frozenset((
    'game_bar_panel_off', 'gamedvr_machine_policy', 'menu_show_delay', 'visual_effects',
    'startup_delay_off', 'system_responsiveness', 'network_throttling_off', 'power_throttling_off',
    'fast_startup_off', 'telemetry_policy_min', 'diagtrack_off', 'vrr_windowed', 'hags',
    'mouse_acceleration_off', 'usb_suspend_off',
    'display_max_refresh', 'all_games_gpu', 'fortnite_gpu', 'fortnite_fullscreen_exclusive',
    'usb_hub_power_off', 'nic_power_saving_off', 'nic_green_ethernet_off', 'nic_rss_on', 'hibernate_off',
))
AGRESSIVO = MAXIMO | frozenset((
    'global_timer_resolution', 'kernel_no_paging', 'fullscreen_exclusive', 'spooler_off',
    'nvme_idle_never', 'nagle_off', 'nic_interrupt_moderation_off', 'gpu_interrupt_priority',
    'ntfs_last_access_off', 'ntfs_short_names_off', 'memory_compression_off',
))
EXTENDED = {'maximo': MAXIMO, 'agressivo': AGRESSIVO}
NEVER_AUTOMATIC = frozenset(('memory_integrity_off', 'defender_game_exclusions', 'gpu_msi',
                             'usb_controller_msi', 'storage_msi'))
# Sem captura transacional própria, mas com verify e revert apoiados no baseline
# que o lote grava antes do primeiro ajuste. Só entram nos modos da tela inicial.
BASELINE_BACKED = frozenset((
    'display_max_refresh', 'all_games_gpu', 'fortnite_gpu', 'fortnite_fullscreen_exclusive',
    'usb_hub_power_off', 'nic_power_saving_off', 'nic_green_ethernet_off', 'nic_rss_on', 'hibernate_off',
    'processor_idle_disable', 'nvme_idle_never', 'nagle_off', 'nic_interrupt_moderation_off',
    'gpu_interrupt_priority', 'ntfs_last_access_off', 'ntfs_short_names_off', 'memory_compression_off',
    'usb_interrupts_ecores',
))

# Consertos do módulo Reparo. Não têm desfazer de propósito: cada um devolve um
# padrão do Windows que outro programa desligou (Proteção do Sistema, firewall,
# serviços essenciais, cache de escrita, TRIM, auto-ajuste TCP, overrides de
# boot). Num PC intacto o `compatible` de cada um responde "nada a reparar" e
# nada roda. Entram nos dois modos da tela inicial porque otimizar em cima de um
# Windows sabotado não entrega o que o botão promete.
REPAIRS = frozenset((
    'system_restore_repair', 'firewall_repair', 'essential_services_repair', 'write_cache_repair',
    'clear_pagefile_repair', 'bcd_timer_repair', 'app_launch_cache_repair', 'tcp_autotuning_repair',
    'trim_repair',
))

# Removed from application, retained in the catalog solely for audit/legacy undo.
REMOVED = {
    'memory_integrity_off':('ARRISCADA','Reduz uma proteção de segurança; fora do escopo gamer seguro.'),
    'defender_game_exclusions':('ARRISCADA','Exclusões amplas enfraquecem a proteção do executável e da pasta do jogo.'),
    'gpu_msi':('ARRISCADA','O driver deve definir o modo de interrupção suportado.'),
    'usb_controller_msi':('ARRISCADA','Não mudar modo de interrupção de controladores de entrada genericamente.'),
    'storage_msi':('ARRISCADA','Alteração de driver de armazenamento exige validação específica.'),
}
# Tirados do lote padrão pela auditoria. Voltam só no modo Agressivo ou com um
# clique explícito, sempre com releitura e reversão.
AGGRESSIVE_ONLY = {
    'kernel_no_paging':('SITUACIONAL','Não há diagnóstico que justifique alterar o gerenciamento do kernel.'),
    'global_timer_resolution':('SITUACIONAL','Não impor temporização global e permanente ao sistema.'),
    'gpu_interrupt_priority':('ARRISCADA','Política de interrupção sem validação do driver e da topologia.'),
    'nagle_off':('SITUACIONAL','TCPAckFrequency global não é ajuste universal de jogos; usar diagnóstico de rede.'),
}
# Fora de qualquer lote, inclusive do Agressivo: placebo, cosmético ou dependente
# de teste A/B do cliente. Continuam aplicáveis com um clique, para quem quiser medir.
AB_TEST_ONLY = {
    'mmcss_games_priority':('PLACEBO','Campos GPU/SFIO não utilizados e prioridade descrita incorretamente; substituir por gerenciamento por processo.'),
    'svchost_split_threshold':('ARRISCADA','Agrupar serviços reduz a contagem sem comprovar menor trabalho e diminui isolamento.'),
    'processor_idle_disable':('ARRISCADA','Com todos os núcleos sempre ativos a CPU fica no turbo de todos os núcleos: num i5-13400F medido, 4,08 GHz em vez de até 4,6 GHz na thread que limita o jogo. Também eleva consumo e calor.'),
    'prefetcher_ssd_off':('ARRISCADA','SSD não justifica desativar cache útil de abertura de programas.'),
    'sysmain_ssd_off':('ARRISCADA','Não desativar serviço de cache apenas pelo tipo do disco.'),
    'win32_priority_separation':('ARRISCADA','Máscara global de escalonamento sem validação por carga; em CPU híbrida (núcleos P e E) atrapalha o agendador do Windows 11.'),
    'tdr_delay':('ARRISCADA','Aumentar timeout pode apenas esconder falha de GPU/driver.'),
    'mpo_off':('SITUACIONAL','Resolve cintilação em parte dos monitores; fora disso não dá FPS e muda como todas as janelas são apresentadas.'),
}
COSMETIC=frozenset(('transparency','widgets','search_highlights_off','windows_suggestions','visual_effects','menu_show_delay','game_bar_panel_off'))
HARDWARE=frozenset(('power_plan','hags','all_games_gpu','fortnite_gpu','vrr_windowed','nic_rss_on','automatic_pagefile'))
KEEP=frozenset(('game_mode','automatic_pagefile','game_dvr','mouse_acceleration_off','transparency','widgets','windows_suggestions'))

def classify(task):
    category='COSMÉTICA' if task.id in COSMETIC else 'BENÉFICA EM HARDWARE ESPECÍFICO' if task.id in HARDWARE else 'BENÉFICA' if task.id=='game_mode' else 'SITUACIONAL'
    return category, 'MANTER' if task.id in KEEP else 'SUBSTITUIR' if task.id in ('latency_timer','game_priority_engine','azor_memory_engine') else 'MELHORAR'

def review(task):
    admin=any(k[0]=='HKLM' for k in task.registry_keys) or task.module in ('services','storage','repair') or task.id in ('power_plan','automatic_pagefile','usb_suspend_off','usb_interrupts_ecores')
    classification,disposition=classify(task)
    task=replace(task,classification=classification,disposition=disposition,requires_admin=admin)
    if task.id in REMOVED:
        classification,reason=REMOVED[task.id]
        return replace(task,apply=None,automatic=False,classification=classification,disposition='REMOVER',audit_reason=reason,
                       description='Retirado da aplicação. '+reason,metric='')
    if task.id in AGGRESSIVE_ONLY:
        classification,reason=AGGRESSIVE_ONLY[task.id]
        return replace(task,automatic=False,classification=classification,disposition='AGRESSIVO',
                       audit_reason='Só no modo Agressivo ou com um clique seu. '+reason)
    if task.id in AB_TEST_ONLY:
        classification,reason=AB_TEST_ONLY[task.id]
        return replace(task,automatic=False,classification=classification,disposition='TESTE A/B',
                       audit_reason='Fora dos lotes automáticos: só como teste seu, medido antes e depois. '+reason)
    reason=MANUAL.get(task.id,'')
    if not task.verify or not task.revert or not task.reversible:
        reason='Ação sem verificação ou reversão completa: disponível somente fora do clique único, com escopo explícito.'
    if task.risk in ('high','experimental'):
        reason=reason or 'Risco avançado ou benefício variável: requer decisão explícita e teste individual.'
    return replace(task, automatic=False, audit_reason=reason) if reason else task

def automatic_decision(task, ctx):
    profile=ctx['resolved_profile']
    if profile in EXTENDED:
        return _extended_decision(task, profile)
    allowed=SAFE if profile=='safe' else ULTRA if profile=='ultra' else COMPETITIVE
    if task.id not in allowed:
        return False, task.audit_reason or 'Preferência ou ação específica: use o módulo correspondente para escolher.'
    if not task.automatic:
        return False,task.audit_reason or 'Ação manual.'
    if task.id=='game_dvr' and profile in ('campanha','stream'):
        return False,'Captura preservada neste perfil.'
    hp=ctx.get('hardware',{})
    if task.id=='power_plan' and (hp.get('battery') or not hp.get('ok')):
        return False,'Energia preservada em notebook ou hardware incompleto; requer escolha explícita.'
    return True,'Compatível com a seleção automática auditada.'

def _extended_decision(task, profile):
    if task.id in NEVER_AUTOMATIC or task.apply is None:
        return False, task.audit_reason or 'Fora de qualquer lote automático.'
    if task.id in REPAIRS:
        if task.verify is None:
            return False, 'Conserto sem releitura: não entra no lote.'
        return True, 'Conserto: devolve o padrão do Windows que outro programa desligou.'
    if task.id not in EXTENDED[profile]:
        return False, task.audit_reason or 'Preferência pessoal: fica para escolha manual.'
    if task.verify is None or task.revert is None or not task.reversible:
        return False, 'Sem releitura ou reversão individual: não entra no lote.'
    return True, 'Incluído no modo ' + ('Agressivo.' if profile == 'agressivo' else 'Máximo.')
