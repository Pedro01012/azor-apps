from __future__ import annotations

from .base import OptimizationTask
from .regtweak import RegSpec, V, compile_specs

MODULE = {
    "id": "gpu",
    "label": "GPU",
    "description": "Preferências de GPU verificaveis: agendamento por hardware, interrupção por mensagem e qual placa cada jogo usa. Não faz overclock nem escreve ajuste de driver não documentado.",
    "automatic": True,
}

GPU_PREF_PATH = r"Software\Microsoft\DirectX\UserGpuPreferences"
GRAPHICS_DRIVERS = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"

# HwSchMode e uma chave fixa e por isso pode ser declarada aqui. As chaves de MSI
# vivem sob o caminho de instancia PCI da placa - que so existe nesta maquina -,
# entao elas entram no baseline pelo backfill no momento da escrita.
DWM = r"SOFTWARE\Microsoft\Windows\Dwm"


def _gpu_admin(core, ctx):
    if not core.is_admin():
        return False, "Este ajuste grava em HKLM e exige o AZOR aberto como administrador."
    return True, "Privilégio de administrador confirmado."


# Tweaks de GPU que são só registro entram pela fábrica declarativa; os que
# dependem de descobrir o caminho da placa nesta máquina continuam à mão.
SPECS = [
    RegSpec(
        id="tdr_delay",
        name="Dar mais tempo à GPU antes do Windows reiniciar o driver",
        # SAIU DO LOTE AUTOMATICO na auditoria.
        #
        # Aumentar o TdrDelay nao evita que a GPU trave: apenas faz o Windows
        # ESPERAR MAIS antes de socorrer. Para quem esta no meio de uma partida,
        # a troca e de 2 segundos de tela congelada por 10 - e nao vem FPS nem
        # frametime nenhum junto.
        #
        # Faz sentido para quem esta com overclock instavel e quer diagnosticar,
        # e por isso continua na lista manual. Nao faz sentido aplicar sem o
        # cliente saber o que esta comprando.
        automatic=False,
        category="GPU / Estabilidade",
        profiles=("competitive", "campanha", "stream"),
        risk="medium",
        restart=True,
        values=[V("HKLM", GRAPHICS_DRIVERS, "TdrDelay", 10),
                V("HKLM", GRAPHICS_DRIVERS, "TdrDdiDelay", 10)],
        compatible=_gpu_admin,
        description="O Windows reinicia o driver de vídeo quando a GPU demora mais de 2 segundos para "
                    "responder. Em compilação de shader e em carga pesada isso dispara sem a placa "
                    "estar travada de verdade — e o resultado é a tela piscando e o jogo caindo. "
                    "Subir para 10 segundos elimina o falso positivo.",
        source="Timeout Detection and Recovery (TDR) — chaves TdrDelay e TdrDdiDelay em "
               "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers, documentadas pela "
               "Microsoft para desenvolvimento de driver de vídeo. Padrão: 2 segundos.",
        trade_off="Se a GPU travar de verdade, a tela fica congelada por 10 segundos em vez de 2 antes "
                  "do Windows recuperar. Não esconde defeito: se o driver está reiniciando por "
                  "instabilidade real, o Stutter Lab continua contando os eventos 4101.",
        metric="Resets de driver de vídeo (evento 4101)",
        tags=("gpu", "stability", "restart"),
    ),
    RegSpec(
        id="vrr_windowed",
        name="Otimizações para jogos em janela e taxa variável",
        category="GPU / Apresentação",
        profiles=("competitive", "campanha", "stream"),
        risk="low",
        values=[V("HKCU", GPU_PREF_PATH, "DirectXUserGlobalSettings",
                  "SwapEffectUpgradeEnable=1;VRROptimizeEnable=1;")],
        description="Liga as duas opções que o Windows 11 oferece em Configurações gráficas: caminho de "
                    "apresentação otimizado para jogos em janela (tira uma cópia de quadro do meio) e "
                    "taxa de atualização variável para títulos que não a suportam sozinhos.",
        source="Configurações > Sistema > Vídeo > Gráficos > Configurações gráficas padrão "
               "(DirectXUserGlobalSettings em HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences).",
        trade_off="Só tem efeito em monitor com taxa variável e em jogo rodando em janela ou janela sem "
                  "borda. Em tela cheia exclusiva não muda nada — e o AZOR diz isso em vez de contar "
                  "como ganho.",
        metric="Latência de apresentação em janela sem borda",
        tags=("gpu", "display"),
        relations=[{"kind": "redundante", "id": "fullscreen_exclusive",
                    "note": "Estas otimizações só valem em janela ou janela sem borda. Com a tela "
                            "cheia exclusiva aplicada, o jogo não passa pelo compositor e elas ficam "
                            "sem efeito — não é conflito, é uma anulando a outra."}],
    ),
    RegSpec(
        id="mpo_off",
        name="Desligar o Multi-Plane Overlay (MPO)",
        category="GPU / Apresentação",
        profiles=("competitive",),
        risk="experimental",
        automatic=False,
        restart=True,
        values=[V("HKLM", DWM, "OverlayTestMode", 5)],
        compatible=_gpu_admin,
        description="O MPO deixa a GPU compor planos separados em vez de um quadro único. Em parte das "
                    "combinações de driver e monitor ele causa piscada, travada ao mover janela e "
                    "cintilação com taxa variável. Desligar é o teste que NVIDIA e Microsoft indicam "
                    "quando esses sintomas aparecem — e é exatamente por isso que ele fica como teste "
                    "A/B seu, não como recomendação.",
        source="OverlayTestMode=5 em HKLM\\SOFTWARE\\Microsoft\\Windows\\Dwm — passo de "
               "diagnóstico publicado pela NVIDIA e reconhecido pela Microsoft para problemas de "
               "cintilação com MPO.",
        trade_off="Sem MPO, a composição volta a passar inteira pela GPU: em vídeo e em janela isso "
                  "custa um pouco mais de trabalho gráfico. Se você não tem o sintoma, não aplique — "
                  "o AZOR não afirma ganho aqui. Exige reiniciar.",
        metric="Cintilação e travadas ao mover janela (sintoma, não número)",
        tags=("gpu", "display", "ab-test", "restart"),
    ),
]

_SPEC_TASKS, _SPEC_KEYS = compile_specs("gpu", SPECS)

KEYS = {
    "hags": [("HKLM", GRAPHICS_DRIVERS, "HwSchMode")],
    **_SPEC_KEYS,
}


def tasks():
    # ---------------- Fortnite (comportamento original preservado) ----------------
    def compatible(core, ctx):
        fort = ctx.get("fortnite") or core.detect_fortnite()
        if not fort.get("exe"):
            return False, "Fortnite não detectado; nenhuma preferência de GPU será criada."
        return True, "Executável real do Fortnite localizado."

    def apply(core, ctx):
        return core.set_fortnite_high_performance_gpu()

    def verify(core, ctx):
        fort = ctx.get("fortnite") or core.detect_fortnite()
        exe = fort.get("exe")
        if not exe:
            return False, "Fortnite não está disponível para releitura."
        pref = core.reg_read("HKCU", GPU_PREF_PATH, str(exe))
        ok = bool(pref.get("exists") and "GpuPreference=2" in str(pref.get("value") or ""))
        return ok, "Preferência GpuPreference=2 relida e confirmada." if ok else "A preferência de GPU não foi confirmada após a gravação."

    def revert(core, ctx):
        base = core.baseline_state().get("fortnite_gpu_pref") or {}
        exe = str(base.get("exe") or (ctx.get("fortnite") or {}).get("exe") or "")
        if not exe:
            return False, "O baseline não registrou nenhum executável do Fortnite; nada foi alterado."
        return core.revert_registry_from_baseline([("HKCU", GPU_PREF_PATH, exe)], "fortnite_gpu")

    # ---------------- Tela cheia exclusiva so do Fortnite ----------------
    def fse_compat(core, ctx):
        fort = ctx.get("fortnite") or core.detect_fortnite()
        if not fort.get("exe"):
            return False, "Fortnite não foi localizado neste PC."
        return True, "Executável do Fortnite localizado."

    def fse_apply(core, ctx):
        return core.set_fortnite_fullscreen_exclusive(True)

    def fse_verify(core, ctx):
        fort = ctx.get("fortnite") or core.detect_fortnite()
        exe = fort.get("exe")
        if not exe:
            return False, "Fortnite não está disponível para releitura."
        val = str(core.reg_read("HKCU", core.APPCOMPAT_LAYERS, str(exe)).get("value") or "")
        ok = core.FSO_OFF_FLAG in val
        return ok, (f"Relido do registro: {val}" if ok
                    else "A flag de tela cheia exclusiva não foi confirmada.")

    def fse_revert(core, ctx):
        fort = ctx.get("fortnite") or core.detect_fortnite()
        exe = str(fort.get("exe") or "")
        if not exe:
            return False, "Sem executável do Fortnite registrado; nada foi alterado."
        return core.revert_registry_from_baseline(
            [("HKCU", core.APPCOMPAT_LAYERS, exe)], "fortnite_fso")

    # ---------------- Todos os jogos encontrados ----------------
    def all_games_compat(core, ctx):
        if not ctx.get("hardware", {}).get("discrete_gpu"):
            return False, ("Este PC tem uma GPU só. A preferência existe para escolher entre integrada e "
                           "dedicada, então aqui ela não teria efeito - e o AZOR não grava o que não muda nada.")
        games = core.detect_installed_games()
        if not games:
            return False, "Nenhum executável de jogo foi localizado nas pastas conhecidas de lancadores."
        return True, f"{len(games)} jogo(s) localizados nas pastas dos lancadores instalados."

    def all_games_apply(core, ctx):
        return core.set_all_games_high_performance_gpu()

    def all_games_verify(core, ctx):
        games = core.detect_installed_games()
        missing = []
        for game in games:
            pref = core.reg_read("HKCU", GPU_PREF_PATH, str(game["exe"]))
            if not (pref.get("exists") and "GpuPreference=2" in str(pref.get("value") or "")):
                missing.append(game["name"])
        ok = not missing
        return ok, (f"{len(games)} jogo(s) relidos com GpuPreference=2." if ok
                    else "Sem confirmação para: " + ", ".join(missing[:6]))

    def all_games_revert(core, ctx):
        games = core.detect_installed_games()
        keys = [("HKCU", GPU_PREF_PATH, str(g["exe"])) for g in games]
        if not keys:
            return False, "Nenhum jogo conhecido para reverter."
        return core.revert_registry_from_baseline(keys, "all_games_gpu")

    # ---------------- Agendamento por hardware ----------------
    def hags_compat(core, ctx):
        if not core.is_admin():
            return False, "Este ajuste grava em HKLM e exige o AZOR aberto como administrador."
        state = core.hags_state()
        if not state.get("supported"):
            return False, ("Este Windows/driver não expõe agendamento de GPU por hardware. A chave nem "
                           "existe, e criar uma chave que o driver ignora seria teatro.")
        if state.get("enabled"):
            return False, "Agendamento de GPU por hardware já está ligado."
        return True, "O driver expõe agendamento por hardware e ele está desligado."

    def hags_apply(core, ctx):
        ok, detail = core.write_registry_values_verified(
            [{"root": "HKLM", "path": GRAPHICS_DRIVERS, "name": "HwSchMode", "value": 2}])
        return ok, (detail + " Só passa a valer depois de reiniciar o Windows." if ok else detail)

    def hags_verify(core, ctx):
        state = core.hags_state()
        ok = bool(state.get("enabled"))
        return ok, ("HwSchMode relido como 2 (ligado)." if ok
                    else f"HwSchMode continua em {state.get('value')}.")

    def hags_revert(core, ctx):
        return core.revert_registry_from_baseline([("HKLM", GRAPHICS_DRIVERS, "HwSchMode")], "hags")

    # ---------------- prioridade de interrup\u00e7\u00e3o ----------------
    def irq_compat(core, ctx):
        state = core.gpu_interrupt_priority_state()
        if not state.get("gpus"):
            return False, "Nenhuma GPU no barramento PCI foi encontrada."
        if state.get("all_high"):
            return False, "As interrup\u00e7\u00f5es da GPU j\u00e1 est\u00e3o em prioridade alta."
        found = "GPU(s): " + ", ".join(g["name"] for g in state["gpus"]) + "."
        if not core.is_admin():
            return False, found + " O ajuste grava no Enum do dispositivo e exige administrador."
        return True, found

    def irq_apply(core, ctx):
        return core.set_gpu_interrupt_priority_verified(True)

    def irq_verify(core, ctx):
        state = core.gpu_interrupt_priority_state()
        ok = bool(state.get("all_high"))
        return ok, ("DevicePriority relido como 3 (alta) em todas as GPUs." if ok
                    else "Nem toda GPU confirmou DevicePriority=3.")

    def irq_revert(core, ctx):
        keys = [("HKLM", core._affinity_policy_path(g["instance"]), "DevicePriority")
                for g in core.gpu_interrupt_priority_state().get("gpus", [])]
        if not keys:
            return False, "Nenhuma GPU para reverter."
        return core.revert_registry_from_baseline(keys, "gpu_interrupt_priority")

    # ---------------- MSI ----------------
    def msi_compat(core, ctx):
        if not core.is_admin():
            return False, "Este ajuste grava no Enum do dispositivo e exige o AZOR como administrador."
        state = core.gpu_msi_state()
        if not state.get("gpus"):
            return False, "Nenhuma GPU no barramento PCI foi encontrada."
        if state.get("all_on"):
            return False, "As GPUs deste PC já usam interrupção por mensagem (MSI)."
        names = ", ".join(g["name"] for g in state["gpus"])
        return True, f"GPU(s) encontradas: {names}."

    def msi_apply(core, ctx):
        return core.set_gpu_msi_verified(True)

    def msi_verify(core, ctx):
        state = core.gpu_msi_state()
        ok = bool(state.get("all_on"))
        return ok, ("MSISupported relido como 1 em todas as GPUs PCI." if ok
                    else "Nem todas as GPUs confirmaram MSISupported=1.")

    def msi_revert(core, ctx):
        keys = [("HKLM", core._msi_path(g["instance"]), "MSISupported")
                for g in core.gpu_msi_state().get("gpus", [])]
        if not keys:
            return False, "Nenhuma GPU PCI para reverter."
        return core.revert_registry_from_baseline(keys, "gpu_msi")

    # ---------------- taxa de atualização ----------------
    def hz_compat(core, ctx):
        state = core.display_refresh_state()
        if not state.get("ok"):
            return False, "O Windows não respondeu o modo de vídeo atual; preservado."
        if not state.get("below_max"):
            return False, (f"O monitor já está em {state.get('current_hz')} Hz, que é a maior taxa "
                           f"deste modo em {state.get('width')}x{state.get('height')}.")
        ganho = int(state.get("max_hz") or 0) - int(state.get("current_hz") or 0)
        return True, (f"O monitor está em {state.get('current_hz')} Hz e aceita {state.get('max_hz')} Hz "
                      f"em {state.get('width')}x{state.get('height')}. São {ganho} quadros por segundo "
                      "a mais que a tela pode mostrar — sem tocar em mais nada.")

    def hz_apply(core, ctx):
        return core.set_display_refresh_verified(int(core.display_refresh_state().get("max_hz") or 0))

    def hz_verify(core, ctx):
        state = core.display_refresh_state()
        ok = state.get("ok") and not state.get("below_max")
        return ok, (f"Modo relido: {state.get('current_hz')} Hz em {state.get('width')}x{state.get('height')}."
                    if ok else f"O Windows ainda reporta {state.get('current_hz')} Hz.")

    def hz_revert(core, ctx):
        saved = core.baseline_state().get("display_refresh") or {}
        original = saved.get("hz")
        if not isinstance(original, int):
            return False, "O baseline não registrou a taxa de atualização anterior."
        return core.set_display_refresh_verified(original)

    return list(_SPEC_TASKS) + [
        OptimizationTask(
            id="fortnite_fullscreen_exclusive",
            name="Tela cheia exclusiva para o Fortnite (só para ele)",
            category="Fortnite",
            module=MODULE["id"],
            profiles=("competitive", "campanha", "stream"),
            risk="low",
            automatic=True,
            compatible=fse_compat,
            apply=fse_apply,
            verify=fse_verify,
            revert=fse_revert,
            description="Tira o compositor do Windows do caminho entre o frame pronto e o monitor, "
                        "gravando a opção APENAS no executável do Fortnite. O AZOR já fazia isso pela "
                        "chave global do GameConfigStore, que vale para todos os aplicativos e derruba "
                        "o overlay do Discord, do OBS e dos capturadores no PC inteiro. Por executável "
                        "o ganho é o mesmo dentro do jogo e o resto do sistema não muda.",
            source="AppCompatFlags\\Layers (HKCU) — é a mesma chave que a caixinha 'Desabilitar "
                   "otimizações de tela cheia' nas Propriedades do executável grava. O cliente "
                   "consegue conferir e desfazer por lá.",
            trade_off="Dentro do Fortnite, overlays que desenham por cima podem não aparecer. Fora "
                      "dele, nada muda — que é justamente a diferença para a versão global.",
            metric="Latência de clique até pixel",
            tags=("fortnite", "latency", "fullscreen"),
        ),
        OptimizationTask(
            "display_max_refresh", "Colocar o monitor na taxa máxima", MODULE["id"],
            "GPU / Monitor", ("safe", "competitive", "campanha", "stream"), risk="low",
            description="Um monitor de 144 Hz ligado a 60 Hz mostra 60 quadros por segundo por mais "
                        "FPS que a placa gere. É a otimização mais barata que existe e a que devolve "
                        "mais que a maioria dos ajustes de registro somados — e até agora o AZOR só "
                        "sabia avisar que estava errado.",
            apply=hz_apply, verify=hz_verify, revert=hz_revert, compatible=hz_compat,
            tags=("display", "fps"),
            source="EnumDisplaySettings / ChangeDisplaySettingsEx — API de modo de vídeo do Windows. "
                   "É o mesmo que Configurações > Sistema > Vídeo > Vídeo avançado > Taxa de "
                   "atualização. O AZOR testa o modo com CDS_TEST antes de aplicar.",
            trade_off="Taxa mais alta consome um pouco mais de energia do monitor e da GPU. Em "
                      "notebook na bateria, alguns modelos reduzem a autonomia de forma perceptível. "
                      "A troca é reversível na hora, sem reiniciar.",
            metric="Quadros por segundo que a tela consegue mostrar",
        ),
        OptimizationTask(
            "fortnite_gpu", "Fortnite na GPU de alto desempenho", MODULE["id"], "GPU / Fortnite",
            ("safe", "competitive", "stream"),
            description="Define o executável detectado para GPU de alto desempenho e rele o registro.",
            apply=apply, verify=verify, revert=revert, compatible=compatible,
            tags=("gpu", "fortnite", "registry"),
            source="Configurações > Sistema > Vídeo > Gráficos do Windows. O AZOR escreve o mesmo valor "
                   "(GpuPreference=2) em HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences e rele para confirmar.",
            trade_off="Só faz diferença em PC com duas GPUs (integrada + dedicada). Em máquina com uma GPU só, "
                      "o AZOR grava a preferência mas nenhum ganho deve ser esperado - e ele diz isso em vez de fingir.",
            metric="FPS medio",
        ),
        OptimizationTask(
            "all_games_gpu", "Todos os jogos na GPU dedicada", MODULE["id"], "GPU / Jogos",
            ("competitive", "campanha", "stream"),
            description="Varre as pastas dos lancadores instalados (Steam, Epic, Riot e bibliotecas em "
                        "outros discos) e grava GpuPreference=2 para cada jogo encontrado, relendo um a um. "
                        "Resolve o caso clássico do jogo que abre na placa integrada sem avisar.",
            apply=all_games_apply, verify=all_games_verify, revert=all_games_revert,
            compatible=all_games_compat, tags=("gpu", "games", "registry"),
            source="Mesma preferência por aplicativo de Configurações > Sistema > Vídeo > Gráficos "
                   "(HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences).",
            trade_off="Jogo leve rodando na dedicada gasta mais energia do que rodaria na integrada. Em "
                      "notebook na bateria, isso encurta a autonomia.",
            metric="FPS medio em jogo que abria na GPU errada",
        ),
        OptimizationTask(
            "hags", "Agendamento de GPU por hardware", MODULE["id"], "GPU / Agendamento",
            ("competitive", "campanha"), risk="medium", restart=True,
            description="Entrega o agendamento da fila de trabalho da GPU ao processador da própria "
                        "placa, tirando uma camada de gerenciamento da CPU. É também o pré-requisito de "
                        "recursos de baixa latência dos drivers atuais.",
            apply=hags_apply, verify=hags_verify, revert=hags_revert, compatible=hags_compat,
            tags=("gpu", "latency", "restart"),
            source="Hardware-Accelerated GPU Scheduling - Microsoft Learn. Chave HwSchMode em "
                   "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers (1 = desligado, 2 = ligado). "
                   "É o mesmo interruptor de Configurações > Vídeo > Gráficos > Configurações gráficas padrão.",
            trade_off="Exige reiniciar. Em drivers antigos ou GPUs de geração mais velha, já causou "
                      "instabilidade em captura de tela e gravação - se aparecer, e um clique para voltar.",
            metric="Latência de renderização e 1% low",
        ),
        OptimizationTask(
            "gpu_interrupt_priority", "Prioridade alta para as interrup\u00e7\u00f5es da GPU", MODULE["id"],
            "GPU / Interrup\u00e7\u00e3o", ("competitive",), risk="medium", restart=True,
            description="Define a prioridade das interrup\u00e7\u00f5es da placa de v\u00eddeo como alta. \u00c9 o passo "
                        "seguinte ao MSI: o MSI tira a GPU da linha compartilhada, este decide quem \u00e9 "
                        "atendido primeiro quando duas interrup\u00e7\u00f5es chegam juntas.",
            apply=irq_apply, verify=irq_verify, revert=irq_revert, compatible=irq_compat,
            tags=("gpu", "dpc", "latency", "restart"),
            source="DevicePriority em ...\\\\Enum\\\\PCI\\\\<inst\u00e2ncia>\\\\Device Parameters\\\\Interrupt "
                   "Management\\\\Affinity Policy \u2014 a mesma chave que a Interrupt Affinity Policy Tool da "
                   "Microsoft grava. 3 = alta.",
            trade_off="Interrup\u00e7\u00e3o de v\u00eddeo passa na frente de outras do sistema. Em PC que grava ou "
                      "transmite ao mesmo tempo, a captura pode perder alguns quadros. Exige reiniciar, "
                      "e volta com um clique.",
            metric="Lat\u00eancia de DPC do driver de v\u00eddeo",
            relations=[{"kind": "amplia", "id": "gpu_msi",
                        "note": "Sem MSI, a GPU divide linha de interrup\u00e7\u00e3o e a prioridade rende "
                                "pouco. Os dois juntos s\u00e3o o ajuste completo de DPC de v\u00eddeo."}],
        ),
        OptimizationTask(
            "gpu_msi", "Interrupção por mensagem (MSI) na GPU", MODULE["id"], "GPU / Interrupção",
            ("competitive",), risk="high", restart=True, automatic=False,
            description="Faz a GPU sinalizar interrupções por mensagem em vez de compartilhar uma linha "
                        "IRQ. É o ajuste com efeito mais direto sobre latência de DPC, e por isso mesmo "
                        "e o mais invasivo: fica fora do lote de um clique e exige um clique seu.",
            apply=msi_apply, verify=msi_verify, revert=msi_revert, compatible=msi_compat,
            tags=("gpu", "dpc", "manual", "restart"),
            source="MSI/MSI-X em PCI Express - especificação PCIe e documentação de driver da Microsoft. "
                   "Chave MSISupported em ...\\Enum\\PCI\\<instância>\\Device Parameters\\Interrupt "
                   "Management\\MessageSignaledInterruptProperties.",
            trade_off="Em hardware antigo ou placa-mãe com ACPI problemático, MSI já causou tela preta no "
                      "boot seguinte. A reversão existe e funciona, mas se o PC não subir com vídeo ela "
                      "tem de ser feita pelo Modo de Segurança. Por isso: alto risco, clique explicito, "
                      "e só depois de ter um ponto de restauração.",
            metric="Latência de DPC do driver de vídeo",
        ),
    ]
