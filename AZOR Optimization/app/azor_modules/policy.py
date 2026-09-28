"""O que entra no BOOST de um clique.

Dois modos, uma regra: desempenho máximo e delay mínimo, sem quebrar o PC.

RECOMENDADO (id interno "maximo")
    Tudo que dá FPS, tira delay, estabiliza o frametime ou tira peso do Windows
    e que o jogador não sente falta: plano de energia, Game Mode, GPU certa,
    monitor na taxa máxima, mouse sem aceleração, USB e rede sem economia,
    serviços e tarefas de telemetria fora do boot, Edge/Copilot/Recall fora da
    memória. Cada item relê o valor e volta com um clique.

EXTREMO (id interno "agressivo")
    O Recomendado mais o que tem custo real para alguém: timer global de
    0,5 ms, tela cheia exclusiva no PC inteiro (overlays podem sumir), placa de
    rede sem moderação (mais CPU), NVMe sempre ativo (mais consumo), antivírus
    fora das pastas de jogo, indexador de pesquisa desligado, núcleo na RAM,
    sem compressão de memória em PC de 32 GB+.

Fora dos dois, de propósito:
  * PIORA o jogo quando medido: CPU sem repouso (derruba o turbo do núcleo que
    roda o jogo), SysMain/Prefetcher desligados (programas abrem do zero),
    quantum do agendador e MMCSS "High" (efeito nulo ou negativo em CPU híbrida),
    MPO e TdrDelay (resolvem sintoma específico, não dão FPS).
  * Pode deixar o PC sem imagem, sem USB ou sem boot: MSI forçado.
  * Reduz segurança e alguns anti-cheats recusam: Integridade de Memória.
Todos continuam na tela Tweaks, a um clique, para quem quiser testar.
"""
from dataclasses import replace

RECOMENDADO = frozenset((
    # Mais FPS
    'power_plan', 'power_throttling_off', 'game_mode', 'game_dvr', 'gamedvr_machine_policy', 'hags',
    'display_max_refresh', 'all_games_gpu', 'fortnite_gpu', 'visual_effects', 'transparency', 'vrr_windowed',
    # Menos delay
    'mouse_acceleration_off', 'usb_suspend_off', 'usb_hub_power_off', 'fortnite_fullscreen_exclusive',
    'sticky_keys_off', 'game_bar_panel_off', 'menu_show_delay', 'end_task_taskbar',
    # Sem travadinhas
    'system_responsiveness', 'network_throttling_off', 'fast_startup_off', 'hibernate_off',
    'automatic_pagefile', 'ntfs_last_access_off',
    # Internet e ping
    'nic_power_saving_off', 'nic_green_ethernet_off', 'nic_rss_on', 'delivery_optimization_off',
    # Windows leve
    'services_lite', 'telemetry_tasks_off', 'diagtrack_off', 'background_apps', 'edge_background_off',
    'copilot_recall_off', 'consumer_features_off', 'widgets', 'search_highlights_off', 'bing_search_off',
    'device_metadata_off', 'windows_suggestions', 'startup_delay_off',
    # Privacidade que também tira processo e rede do fundo
    'telemetry_policy_min', 'telemetry_full_off', 'activity_history_off',
))

EXTREMO = RECOMENDADO | frozenset((
    'global_timer_resolution', 'kernel_no_paging', 'fullscreen_exclusive', 'spooler_off', 'nvme_idle_never',
    'nagle_off', 'nic_interrupt_moderation_off', 'gpu_interrupt_priority', 'ntfs_short_names_off',
    'memory_compression_off', 'services_extreme', 'defender_game_exclusions',
))

# Nomes internos preservados: os estados salvos e a tarefa de login usam estes ids.
MAXIMO, AGRESSIVO = RECOMENDADO, EXTREMO
EXTENDED = {'maximo': RECOMENDADO, 'agressivo': EXTREMO}
MODE_LABELS = {'maximo': 'RECOMENDADO', 'agressivo': 'EXTREMO'}

# Quem faz live marca isso nos Ajustes. Tela cheia exclusiva derruba overlay do
# Discord e de alguns capturadores; o resto do BOOST continua igual.
STREAMER_SKIP = frozenset(('fullscreen_exclusive', 'fortnite_fullscreen_exclusive'))

NEVER_AUTOMATIC = frozenset(('memory_integrity_off', 'gpu_msi', 'usb_controller_msi', 'storage_msi',
                             'bitlocker_off', 'reserved_storage_off'))

# Sem captura transacional própria, mas com releitura e reversão apoiadas no
# baseline gravado antes do lote (ou num registro próprio do módulo).
BASELINE_BACKED = frozenset((
    'display_max_refresh', 'all_games_gpu', 'fortnite_gpu', 'fortnite_fullscreen_exclusive',
    'usb_hub_power_off', 'nic_power_saving_off', 'nic_green_ethernet_off', 'nic_rss_on', 'hibernate_off',
    'processor_idle_disable', 'nvme_idle_never', 'nagle_off', 'nic_interrupt_moderation_off',
    'gpu_interrupt_priority', 'ntfs_last_access_off', 'ntfs_short_names_off', 'memory_compression_off',
    'usb_interrupts_ecores', 'telemetry_tasks_off', 'classic_context_menu', 'reserved_storage_off',
    'defender_game_exclusions', 'visual_effects',
))

# Consertos: devolvem o padrão do Windows que outro programa desligou. Não têm
# desfazer de propósito (desfazer seria religar o defeito).
REPAIRS = frozenset((
    'system_restore_repair', 'firewall_repair', 'essential_services_repair', 'write_cache_repair',
    'clear_pagefile_repair', 'bcd_timer_repair', 'app_launch_cache_repair', 'tcp_autotuning_repair',
    'trim_repair',
))

# Ações de mão única, só manuais e com o custo escrito antes do clique.
ONE_WAY = frozenset(('bitlocker_off',))

# Existem na tela Tweaks para teste do próprio usuário. Nunca entram em lote.
AB_TEST_ONLY = {
    'mmcss_games_priority': ('PLACEBO', 'Os campos GPU Priority e SFIO Priority nem são usados pelo Windows.'),
    'svchost_split_threshold': ('ARRISCADA', 'Menos processos na lista, nenhum FPS a mais, menos estabilidade.'),
    'processor_idle_disable': ('ARRISCADA', 'Medido num i5-13400F: o turbo do núcleo do jogo caiu de 4,6 para 4,08 GHz.'),
    'prefetcher_ssd_off': ('ARRISCADA', 'Programas passam a abrir do zero, mesmo em SSD.'),
    'sysmain_ssd_off': ('ARRISCADA', 'Programas passam a abrir do zero, mesmo em SSD.'),
    'win32_priority_separation': ('ARRISCADA', 'Em CPU híbrida atrapalha o agendador do Windows 11; já travou o Fortnite.'),
    'tdr_delay': ('ARRISCADA', 'Só esconde driver instável por mais tempo.'),
    'mpo_off': ('SITUACIONAL', 'Resolve tela piscando; fora disso não dá FPS e já travou jogos em tela cheia.'),
}

REMOVED_REASON = {
    'gpu_msi': 'Drivers atuais já usam MSI; forçar pode deixar o PC sem imagem.',
    'usb_controller_msi': 'Pode deixar o PC sem mouse e teclado no próximo boot.',
    'storage_msi': 'Pode impedir o PC de ligar.',
}


def classify(task_id):
    if task_id in REPAIRS:
        return 'CONSERTO'
    if task_id in AB_TEST_ONLY:
        return AB_TEST_ONLY[task_id][0]
    if task_id in NEVER_AUTOMATIC:
        return 'ARRISCADA'
    if task_id in RECOMENDADO:
        return 'RECOMENDADO'
    if task_id in EXTREMO:
        return 'EXTREMO'
    return 'OPCIONAL'


def review(task):
    admin = (any(k[0] == 'HKLM' for k in task.registry_keys)
             or task.module in ('services', 'storage', 'repair', 'lite')
             or task.id in ('power_plan', 'automatic_pagefile', 'usb_suspend_off', 'usb_interrupts_ecores'))
    classification = classify(task.id)
    disposition = ('RECOMENDADO' if task.id in RECOMENDADO else 'EXTREMO' if task.id in EXTREMO
                   else 'TESTE A/B' if task.id in AB_TEST_ONLY else 'MANUAL')
    task = replace(task, classification=classification, disposition=disposition, requires_admin=admin)
    if task.id in AB_TEST_ONLY:
        return replace(task, automatic=False, audit_reason='Fora do BOOST: ' + AB_TEST_ONLY[task.id][1])
    if task.id in REMOVED_REASON:
        return replace(task, automatic=False, audit_reason='Fora do BOOST: ' + REMOVED_REASON[task.id])
    if task.id not in EXTREMO and task.id not in REPAIRS:
        return replace(task, automatic=False, audit_reason=task.audit_reason or 'Opcional: aplique pela tela Tweaks.')
    return task


def automatic_decision(task, ctx):
    """Entra no lote deste modo?"""
    profile = ctx.get('resolved_profile')
    wanted = EXTENDED.get(profile, RECOMENDADO)
    if task.apply is None or task.id in NEVER_AUTOMATIC:
        return False, task.audit_reason or 'Fora de qualquer lote automático.'
    if task.id in REPAIRS:
        if task.verify is None:
            return False, 'Conserto sem releitura: não entra no lote.'
        return True, 'Conserto: devolve o padrão do Windows que outro programa desligou.'
    if task.id not in wanted:
        return False, task.audit_reason or 'Opcional: aplique pela tela Tweaks.'
    if ctx.get('streamer') and task.id in STREAMER_SKIP:
        return False, 'Preservado porque você marcou que faz live (overlay do Discord e da captura).'
    if task.verify is None or task.revert is None or not task.reversible:
        return False, 'Sem releitura ou sem desfazer: não entra no lote.'
    return True, 'Incluído no modo ' + MODE_LABELS.get(profile, 'RECOMENDADO').capitalize() + '.'
