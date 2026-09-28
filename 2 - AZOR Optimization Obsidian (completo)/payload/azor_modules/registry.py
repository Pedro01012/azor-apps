from __future__ import annotations

from .base import OptimizationTask

MODULE = {
    "id": "registry",
    "label": "Windows & Registro",
    "description": "Preferências de jogos e interface do usuário que podem ser gravadas e relidas.",
    "automatic": True,
}

# Cada tweak declara exatamente quais valores ele escreve. A reversão individual
# usa esta mesma lista contra o baseline anterior ao AZOR, em vez de "adivinhar"
# qual seria o padrão do Windows.
KEYS = {
    "game_mode": [
        ("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode"),
        ("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled"),
    ],
    "game_dvr": [
        ("HKCU", r"System\GameConfigStore", "GameDVR_Enabled"),
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled"),
    ],
    "windows_suggestions": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338388Enabled"),
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-353694Enabled"),
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SystemPaneSuggestionsEnabled"),
    ],
    "transparency": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency"),
    ],
    "widgets": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarDa"),
        # Onde o Windows bloqueia TaskbarDa, o item usa a politica "Permitir widgets".
        ("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests"),
    ],
    "background_apps": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled"),
    ],
    "visual_effects": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting"),
    ],
    "startup_delay_off": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize", "StartupDelayInMSec"),
    ],
    "search_highlights_off": [
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\SearchSettings", "IsDynamicSearchBoxEnabled"),
    ],
    "game_bar_panel_off": [
        ("HKCU", r"Software\Microsoft\GameBar", "ShowStartupPanel"),
        ("HKCU", r"Software\Microsoft\GameBar", "UseNexusForGameBarEnabled"),
    ],
}


def _revert(task_id: str):
    def run(core, ctx):
        return core.revert_registry_from_baseline(KEYS[task_id], task_id)
    return run


def tasks():
    def verify_game_mode(core, ctx):
        ok = bool(core.verify_game_mode())
        return ok, "Game Mode relido como ativado." if ok else "Game Mode não foi confirmado após a gravação."

    def verify_game_dvr(core, ctx):
        ok = bool(core.verify_game_dvr_off())
        return ok, "Game DVR/captura relido como desativado." if ok else "Game DVR/captura não foi confirmado como desativado."

    def verify_suggestions(core, ctx):
        ok = bool(core.verify_windows_suggestions_off())
        return ok, "Sugestões do Windows relidas como desativadas." if ok else "Sugestões do Windows não foram confirmadas como desativadas."

    def verify_transparency(core, ctx):
        ok = bool(core.verify_transparency_off())
        return ok, "Transparência relida como desativada." if ok else "Transparência não foi confirmada como desativada."

    def verify_widgets(core, ctx):
        ok = bool(core.verify_widgets_hidden())
        return ok, "Widgets relidos como ocultos." if ok else "Widgets não foram confirmados como ocultos."

    def verify_background(core, ctx):
        v = core.reg_read("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled")
        ok = v.get("value") == 1
        return ok, "Preferência global de apps em segundo plano relida como desativada." if ok else "O Windows não confirmou a preferência de apps em segundo plano."

    def verify_visual(core, ctx):
        v = core.reg_read("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting")
        ok = v.get("value") == 2
        return ok, "Preset de efeitos visuais relido. Isto não comprova cada animação efetivamente desativada." if ok else "A preferência de efeitos visuais não foi confirmada."

    def verify_startup_delay(core, ctx):
        v = core.reg_read("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize", "StartupDelayInMSec")
        ok = v.get("value") == 0
        return ok, ("Atraso de inicialização relido em zero." if ok
                    else f"O Windows reporta {v.get('value')}.")

    def verify_search_highlights(core, ctx):
        v = core.reg_read("HKCU", r"Software\Microsoft\Windows\CurrentVersion\SearchSettings", "IsDynamicSearchBoxEnabled")
        ok = v.get("value") == 0
        return ok, ("Destaques da pesquisa relidos como desativados." if ok
                    else f"O Windows reporta {v.get('value')}.")

    def verify_game_bar_panel(core, ctx):
        panel = core.reg_read("HKCU", r"Software\Microsoft\GameBar", "ShowStartupPanel")
        nexus = core.reg_read("HKCU", r"Software\Microsoft\GameBar", "UseNexusForGameBarEnabled")
        ok = panel.get("value") == 0 and nexus.get("value") == 0
        return ok, ("Painel inicial da Game Bar relido como desativado." if ok
                    else f"O Windows reporta {panel.get('value')}.")

    def _write(entries):
        def run(core, ctx):
            return core.write_registry_values_verified(entries)
        return run

    return [
        OptimizationTask(
            "game_mode", "Priorizar o jogo em primeiro plano", MODULE["id"], "Windows / Jogos", ("safe", "competitive", "campanha", "stream"),
            description="Ativa o Game Mode e exige releitura do estado.",
            apply=lambda c, x: c.set_game_mode_verified(True), verify=verify_game_mode, revert=_revert("game_mode"),
            tags=("registry", "gaming"),
            source="Game Mode do Windows (Configurações > Jogos > Modo de Jogo). Chaves HKCU\\Software\\Microsoft\\GameBar.",
            trade_off="Praticamente nenhum. O Windows adia atualizações e reduz atividade de segundo plano durante o jogo.",
            metric="Consistência de frametime (p99)",
        ),
        OptimizationTask(
            "game_dvr", "Desligar a gravação em segundo plano", MODULE["id"], "Windows / Jogos", ("safe", "competitive", "stream"),
            description="Desativa captura em segundo plano suportada e confirma o resultado. Fora do perfil CAMPANHA: quem joga história costuma querer a gravação ligada para salvar momentos.",
            apply=lambda c, x: c.set_game_dvr_verified(False), verify=verify_game_dvr, revert=_revert("game_dvr"),
            tags=("registry", "capture"),
            source="Xbox Game Bar / Capturas (Configurações > Jogos > Capturas). GameDVR_Enabled e AppCaptureEnabled, ambos por usuário.",
            trade_off="Você perde o 'gravar os últimos 30 segundos'. Se usa esse recurso, mantenha ligado.",
            metric="FPS médio e 1% low",
        ),
        OptimizationTask(
            "windows_suggestions", "Desligar sugestões promocionais", MODULE["id"], "Windows / Interface", ("safe", "competitive", "campanha", "stream"),
            description="Desativa sugestões promocionais do usuário atual.",
            apply=lambda c, x: c.set_windows_suggestions_off(), verify=verify_suggestions, revert=_revert("windows_suggestions"),
            tags=("registry", "ui"),
            source="ContentDeliveryManager, o mesmo que Configurações > Personalização > Iniciar desliga.",
            trade_off="Nenhum desempenho é prometido aqui: isso remove propaganda, não gera FPS.",
            metric="",
        ),
        OptimizationTask(
            "transparency", "Desligar transparência da interface", MODULE["id"], "Windows / Interface", ("safe", "competitive", "campanha", "stream"),
            description="Desativa transparência visual e relê o valor.",
            apply=lambda c, x: c.set_transparency_off(), verify=verify_transparency, revert=_revert("transparency"),
            tags=("registry", "ui"),
            source="Configurações > Personalização > Cores > Efeitos de transparência (EnableTransparency).",
            trade_off="Windows fica com aparência mais simples. Alivia a GPU no desktop, não dentro do jogo em tela cheia.",
            metric="Uso de GPU no desktop",
        ),
        OptimizationTask(
            "background_apps", "Reduzir apps em segundo plano", MODULE["id"], "Windows / Background", ("competitive",),
            risk="medium", description="Desabilita a preferência de execução em segundo plano dos apps Windows compatíveis. Pode atrasar notificações; não fecha programas Win32, drivers ou antivírus.",
            apply=lambda c, x: c.set_background_apps_verified(True), verify=verify_background, revert=_revert("background_apps"),
            tags=("registry", "background"),
            source="Preferência global de apps em segundo plano (BackgroundAccessApplications\\GlobalUserDisabled).",
            trade_off="Apps da Store deixam de atualizar sozinhos: notificação de mensagem, e-mail e alarme podem atrasar.",
            metric="Processos ativos e uso de CPU em repouso",
        ),
        OptimizationTask(
            "visual_effects", "Priorizar desempenho nos efeitos visuais", MODULE["id"], "Windows / Interface", ("competitive", "stream"),
            risk="medium", description="Prioriza efeitos visuais de desempenho em perfis que pedem responsividade. O CAMPANHA preserva a aparência do Windows.",
            apply=lambda c, x: c.set_visual_effects_verified(True), verify=verify_visual, revert=_revert("visual_effects"),
            tags=("registry", "ui"),
            source="Opções de Desempenho do Windows (VisualFXSetting=2, 'Ajustar para obter melhor desempenho').",
            trade_off="Animações, sombras e suavização de fonte mudam. É a alteração mais visível de todas.",
            metric="Responsividade da área de trabalho",
        ),
        OptimizationTask(
            "widgets", "Ocultar Widgets da barra de tarefas", MODULE["id"], "Windows / Background", ("competitive", "campanha"),
            description="Oculta os Widgets e confirma. Onde o Windows bloqueia a chave do usuário, usa a política oficial Permitir widgets, que também desliga o recurso.",
            apply=lambda c, x: c.set_widgets_taskbar_hidden(), verify=verify_widgets, revert=_revert("widgets"),
            tags=("registry", "background"),
            source="Configurações > Personalização > Barra de tarefas > Widgets (TaskbarDa) e a política Permitir widgets (AllowNewsAndInterests, Componentes do Windows > Widgets).",
            trade_off="O botão de clima/notícias fica oculto. Isso não desinstala Widgets nem comprova que seus processos foram encerrados.",
            metric="Preferência visual da barra de tarefas",
        ),
        OptimizationTask(
            "startup_delay_off", "Remover o atraso de inicialização do Windows", MODULE["id"],
            "Windows / Interface", ("competitive", "campanha", "stream"),
            description="O Explorer segura os programas de inicialização por alguns segundos depois "
                        "do login, para a área de trabalho aparecer antes. Zerar isso deixa o PC "
                        "utilizável mais cedo, ao custo de um login mais movimentado.",
            apply=_write([{"root": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize",
                           "name": "StartupDelayInMSec", "value": 0}]),
            verify=verify_startup_delay, revert=_revert("startup_delay_off"),
            tags=("registry", "boot"),
            source="StartupDelayInMSec em HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\"
                   "Explorer\\Serialize. O atraso padrão do Windows é de cerca de 10 segundos.",
            trade_off="Tudo que inicia junto com o Windows passa a disputar disco e CPU ao mesmo "
                      "tempo do login. Em PC com muitos programas de inicialização e disco mecânico, "
                      "a área de trabalho pode demorar mais para responder.",
            metric="Tempo até o PC ficar utilizável depois do login",
        ),
        OptimizationTask(
            "search_highlights_off", "Desligar os destaques da pesquisa", MODULE["id"],
            "Windows / Interface", ("competitive", "campanha", "stream"),
            description="Os destaques da caixa de pesquisa buscam conteúdo na internet de tempos em "
                        "tempos. Desligar tira um consumidor periódico de rede e CPU que não serve "
                        "para nada durante o jogo.",
            apply=_write([{"root": "HKCU", "path": r"Software\Microsoft\Windows\CurrentVersion\SearchSettings",
                           "name": "IsDynamicSearchBoxEnabled", "value": 0}]),
            verify=verify_search_highlights, revert=_revert("search_highlights_off"),
            tags=("registry", "background"),
            source="Configurações > Privacidade e segurança > Permissões de pesquisa > Destaques da "
                   "pesquisa (IsDynamicSearchBoxEnabled).",
            trade_off="A caixa de pesquisa deixa de mostrar sugestões e datas comemorativas. A busca "
                      "local por arquivos e programas continua igual.",
            metric="Uso de rede e CPU em repouso",
        ),
        OptimizationTask(
            "game_bar_panel_off", "Não abrir o painel da Game Bar ao iniciar o jogo", MODULE["id"],
            "Windows / Jogos", ("competitive", "campanha"),
            description="Impede o painel inicial da Game Bar de aparecer quando um jogo abre. É o "
                        "aviso que rouba o foco no primeiro segundo da partida.",
            apply=_write([
                {"root": "HKCU", "path": r"Software\Microsoft\GameBar", "name": "ShowStartupPanel", "value": 0},
                {"root": "HKCU", "path": r"Software\Microsoft\GameBar", "name": "UseNexusForGameBarEnabled", "value": 0},
            ]),
            verify=verify_game_bar_panel, revert=_revert("game_bar_panel_off"),
            tags=("registry", "gaming"),
            source="Configurações > Jogos > Xbox Game Bar (ShowStartupPanel em "
                   "HKCU\\Software\\Microsoft\\GameBar).",
            trade_off="O atalho Win+G continua funcionando; só o painel automático deixa de abrir "
                      "sozinho. Se você usa a Game Bar para gravar, prefira mantê-lo.",
            metric="Perda de foco no início da partida",
        ),
    ]
