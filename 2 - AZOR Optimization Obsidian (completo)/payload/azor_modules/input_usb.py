from __future__ import annotations

from .base import OptimizationTask

MODULE = {
    "id": "input_usb",
    "label": "Input & Memória",
    "description": "Timer, aceleração de ponteiro, energia das portas USB e AZOR Memory Engine. Ajustes físicos de polling/deadzone continuam dependentes do periférico.",
    "automatic": True,
}

MOUSE_PATH = r"Control Panel\Mouse"
KEYBOARD_PATH = r"Control Panel\Keyboard"

# Estas chaves já eram capturadas pelo baseline desde a primeira versão; agora
# existe um tweak que as escreve, e ele declara exatamente as mesmas.
KEYS = {
    "mouse_acceleration_off": [
        ("HKCU", MOUSE_PATH, "MouseSpeed"),
        ("HKCU", MOUSE_PATH, "MouseThreshold1"),
        ("HKCU", MOUSE_PATH, "MouseThreshold2"),
    ],
    "keyboard_repeat_fast": [
        ("HKCU", KEYBOARD_PATH, "KeyboardDelay"),
        ("HKCU", KEYBOARD_PATH, "KeyboardSpeed"),
    ],
}


def tasks():
    def verify_timer(core, ctx):
        st=core.latency_engine_status();actual=st.get("actual_ms")
        ok=bool(st.get("active")) and (actual is None or float(actual)<=1.05)
        return ok, (f"Timer ativo; Windows reporta {actual} ms." if ok else f"Timer não confirmado: {st}")

    def revert_timer(core, ctx):
        ok, detail = core.disable_latency_engine()
        st = core.latency_engine_status()
        released = not bool(st.get("active"))
        core.journal("revert_timer", ok=bool(ok and released), actual_ms=st.get("actual_ms"))
        return bool(ok and released), (detail if released else "O pedido de timer não foi liberado; o valor continua ativo.")

    def compatible_memory(core, ctx):
        info=core.detect_external_islc_process()
        return True, f"AZOR Memory Engine interno disponível: {info.get('name') or 'AZOR Memory Engine'}."

    def verify_memory(core, ctx):
        info=core.detect_external_islc_process()
        ok=bool(info.get("running"))
        return ok, ("AZOR Memory Engine interno confirmado em execução." if ok else f"Memory Engine não pôde ser confirmado: {info}")

    def revert_memory(core, ctx):
        ok, detail = core.MEMORY_ENGINE.stop()
        core.journal("revert_memory_engine", ok=bool(ok))
        return ok, detail

    def _mouse_values(core):
        return tuple(str(core.reg_read("HKCU", MOUSE_PATH, n).get("value"))
                     for n in ("MouseSpeed", "MouseThreshold1", "MouseThreshold2"))

    def compatible_mouse_accel(core, ctx):
        if _mouse_values(core) == ("0", "0", "0"):
            return False, "A aceleração de ponteiro já está desligada."
        return True, "Aceleração de ponteiro ativa; pode ser desligada e revertida."

    def verify_mouse_accel(core, ctx):
        got = _mouse_values(core)
        ok = got == ("0", "0", "0")
        return ok, ("Os três valores de aceleração do Windows foram relidos em zero." if ok
                    else f"Releitura fora do esperado: {got}.")

    def revert_mouse_accel(core, ctx):
        return core.revert_registry_from_baseline(KEYS["mouse_acceleration_off"], "mouse_acceleration_off")

    def compatible_usb_suspend(core, ctx):
        state = core.get_usb_selective_suspend_state()
        if state is None:
            return False, "O Windows não expôs um estado verificável de suspensão de USB; preservado."
        if state.get("ac") == 0:
            return False, "A suspensão seletiva de USB já está desligada na tomada."
        return True, f"Suspensão seletiva ativa (AC={state.get('ac')}); pode ser desligada e revertida."

    def verify_usb_suspend(core, ctx):
        state = core.get_usb_selective_suspend_state()
        ok = bool(state) and state.get("ac") == 0
        return ok, ("Suspensão seletiva de USB relida como desligada no plano ativo." if ok
                    else f"O powercfg ainda reporta {state}.")

    def revert_usb_suspend(core, ctx):
        original = core.baseline_state().get("usb_selective_suspend")
        if not isinstance(original, dict):
            return False, "O baseline não registrou o estado anterior de suspensão de USB; nada foi alterado."
        ok, detail = core._set_usb_selective_suspend_indexes(int(original.get("ac", 1)), int(original.get("dc", 1)))
        core.journal("revert_usb_suspend", requested=original, ok=ok)
        return ok, detail

    def _usb_controllers(core):
        return core.pci_instances("USB", "pci:usb")

    def compatible_usb_msi(core, ctx):
        devices = _usb_controllers(core)
        if not devices:
            return False, "Nenhum controlador USB no barramento PCI foi encontrado."
        state = core.device_msi_state(devices)
        if state.get("all_on"):
            return False, "Os controladores USB deste PC já usam interrupção por mensagem."
        found = "Controlador(es): " + ", ".join(d["name"] for d in devices[:2]) + "."
        if not core.is_admin():
            return False, found + " O ajuste grava no Enum do dispositivo e exige administrador."
        return True, found

    def apply_usb_msi(core, ctx):
        return core.set_device_msi_verified(_usb_controllers(core), True)

    def verify_usb_msi(core, ctx):
        state = core.device_msi_state(_usb_controllers(core))
        ok = bool(state.get("all_on"))
        return ok, ("MSISupported relido como 1 em todos os controladores USB." if ok
                    else "Nem todo controlador USB confirmou MSISupported=1.")

    def revert_usb_msi(core, ctx):
        keys = [("HKLM", core._msi_path(d["instance"]), "MSISupported") for d in _usb_controllers(core)]
        if not keys:
            return False, "Nenhum controlador USB para reverter."
        return core.revert_registry_from_baseline(keys, "usb_controller_msi")

    def compatible_usb_hubs(core, ctx):
        state = core.usb_hub_power_state()
        if not state.get("hubs"):
            return False, "Nenhum hub USB foi encontrado neste PC; preservado."
        if state.get("all_off"):
            return False, "Todos os hubs USB já estão fora da economia de energia."
        if not core.is_admin():
            return False, (f"{len(state.get('managed') or [])} hub(s) USB ainda podem ser desligados "
                           "pelo Windows. O ajuste grava em HKLM e exige o AZOR como administrador.")
        return True, f"{len(state.get('managed') or [])} hub(s) USB sob economia de energia."

    def verify_usb_hubs(core, ctx):
        state = core.usb_hub_power_state()
        ok = bool(state.get("all_off"))
        return ok, ("Todos os hubs USB relidos fora da economia de energia." if ok
                    else f"{len(state.get('managed') or [])} hub(s) ainda sob economia.")

    def revert_usb_hubs(core, ctx):
        keys = [("HKLM", core._usb_power_path(h["instance"]), "EnhancedPowerManagementEnabled")
                for h in (core.usb_hub_power_state().get("hubs") or [])]
        if not keys:
            return False, "Nenhum hub USB para reverter."
        return core.revert_registry_from_baseline(keys, "usb_hub_power_off")

    def verify_keyboard_repeat(core, ctx):
        delay = str(core.reg_read("HKCU", KEYBOARD_PATH, "KeyboardDelay").get("value"))
        speed = str(core.reg_read("HKCU", KEYBOARD_PATH, "KeyboardSpeed").get("value"))
        ok = delay == "0" and speed == "31"
        return ok, (f"Repetição relida: atraso {delay}, velocidade {speed}." if ok
                    else f"Releitura fora do esperado: atraso {delay}, velocidade {speed}.")

    def revert_keyboard_repeat(core, ctx):
        return core.revert_registry_from_baseline(KEYS["keyboard_repeat_fast"], "keyboard_repeat_fast")

    # ---------------- interrupções do USB nos núcleos E ----------------
    def usbirq_compat(core, ctx):
        state = core.usb_interrupt_affinity_state()
        if not state.get("hybrid"):
            return False, "Este processador não tem núcleos E (não é híbrido); o ajuste não se aplica."
        if not state.get("hosts"):
            return False, "Nenhum controle de jogo conectado por USB agora. Conecte o controle e releia."
        if state.get("all_on_ecores"):
            return False, "As interrupções da controladora do controle já estão nos núcleos E."
        return True, "Controle(s) em: " + ", ".join(h["name"] for h in state["hosts"]) + "."

    def usbirq_verify(core, ctx):
        ok = bool(core.usb_interrupt_affinity_state().get("all_on_ecores"))
        return ok, ("Afinidade relida: interrupções da controladora do controle nos núcleos E." if ok
                    else "A afinidade nos núcleos E não foi confirmada.")

    return [
        OptimizationTask(
            "latency_timer", "Timer de alta resolução", MODULE["id"], "Input / Timer", ("competitive","campanha","stream"),
            risk="low", reversible=True, description="Solicita 0,5 ms pela API nativa e consulta o valor realmente reportado pelo Windows.",
            apply=lambda c,x:c.set_latency_target(0.5), verify=verify_timer, revert=revert_timer,
            tags=("timer","latency","session"),
            source="NtSetTimerResolution / NtQueryTimerResolution (ntdll). Não é API documentada publicamente pela "
                   "Microsoft: por isso o AZOR nunca afirma o valor pedido, e sim o valor que NtQueryTimerResolution devolve.",
            trade_off="O pedido dura só enquanto o AZOR está aberto — é sessão, não alteração permanente. "
                      "Timer mais fino aumenta o número de interrupções e, em notebook na bateria, consome mais.",
            metric="Jitter de execução (µs) medido no AZOR Scope",
        ),
        OptimizationTask(
            "azor_memory_engine", "AZOR Memory Engine", MODULE["id"], "Input / Memória", ("competitive","campanha","stream"),
            risk="low", reversible=True, description="Motor interno adaptativo de standby memory; não depende de executável externo.",
            apply=lambda c,x:c.ensure_external_islc_running(), verify=verify_memory, revert=revert_memory, compatible=compatible_memory,
            tags=("memory","latency","session","internal"),
            source="NtSetSystemInformation(SystemMemoryListInformation, MemoryPurgeStandbyList), a mesma chamada que o "
                   "ISLC usa. Exige SeProfileSingleProcessPrivilege e, portanto, o AZOR como administrador.",
            trade_off="Limpar a standby list joga fora cache útil: o que foi descartado volta a ser lido do disco. "
                      "Por isso o motor só age sob pressão de memória, com intervalo mínimo de 20 s — e o ganho tem de "
                      "aparecer no p99 do frametime, não no número de MB livres.",
            metric="p99 de frametime durante pressão de memória",
        ),
        OptimizationTask(
            "mouse_acceleration_off", "Desligar a aceleração de ponteiro", MODULE["id"], "Input / Mouse",
            ("competitive", "campanha", "stream"),
            risk="low",
            description="Zera MouseSpeed e os dois limiares de aceleração do Windows, para que a mesma "
                        "distância física do mouse dê sempre a mesma distância na tela. É a base de qualquer "
                        "memória muscular de mira.",
            apply=lambda c, x: c.set_enhanced_pointer_precision(False), verify=verify_mouse_accel,
            revert=revert_mouse_accel, compatible=compatible_mouse_accel,
            tags=("mouse", "aim", "registry"),
            source="Melhorar a precisão do ponteiro (Enhanced Pointer Precision), em Configurações > "
                   "Bluetooth e dispositivos > Mouse. Chaves MouseSpeed, MouseThreshold1 e MouseThreshold2 "
                   "em HKCU\\Control Panel\\Mouse.",
            trade_off="Fora do jogo, o ponteiro passa a exigir mais movimento para atravessar a tela em DPI "
                      "baixo. Quem usa o PC para desenho ou planilha em monitor grande pode estranhar.",
            metric="Consistência de mira (mesma distância física = mesma distância na tela)",
        ),
        OptimizationTask(
            "usb_suspend_off", "Impedir o Windows de suspender as portas USB", MODULE["id"], "Input / USB",
            ("safe", "competitive", "campanha", "stream"),
            risk="low",
            description="Desliga a suspensão seletiva de USB no plano ativo. É a causa clássica do mouse ou "
                        "do headset que 'dorme' e demora um instante para responder depois de alguns segundos "
                        "parado. Em notebook, só o índice de tomada é alterado.",
            apply=lambda c, x: c.set_usb_selective_suspend_disabled(True), verify=verify_usb_suspend,
            revert=revert_usb_suspend, compatible=compatible_usb_suspend,
            tags=("usb", "power", "input"),
            source="Suspensão seletiva de USB (subgrupo 2a737441…, ajuste 48e6b7a6…) no powercfg — "
                   "https://learn.microsoft.com/windows-hardware/design/device-experiences/powercfg-command-line-options",
            trade_off="Portas USB deixam de entrar em economia, o que consome um pouco mais de energia. Em "
                      "notebook na bateria o AZOR preserva o valor de bateria e altera só o de tomada.",
            metric="Atraso do primeiro movimento após o periférico ficar parado",
        ),
        OptimizationTask(
            "usb_controller_msi", "Interrupção por mensagem (MSI) no controlador USB", MODULE["id"],
            "Input / USB", ("competitive",), risk="high", restart=True, automatic=False,
            description="Mesmo mecanismo do MSI da GPU, aplicado ao controlador xHCI da placa-mãe. "
                        "Toda tecla e todo movimento do mouse chegam por ele: tirar a interrupção da "
                        "linha compartilhada reduz a latência de DPC do caminho de entrada inteiro.",
            apply=apply_usb_msi, verify=verify_usb_msi, revert=revert_usb_msi,
            compatible=compatible_usb_msi, tags=("usb", "dpc", "manual", "restart", "latency"),
            source="MSI/MSI-X em PCI Express - chave MSISupported em ...\\Enum\\PCI\\<instancia>"
                   "\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties.",
            trade_off="Mesmo risco do MSI na GPU: em placa-mãe com ACPI problemático, o controlador "
                      "pode não inicializar no boot seguinte - e sem USB não há teclado nem mouse para "
                      "consertar. A reversão existe, mas precisaria de Modo de Segurança. Alto risco, "
                      "clique explicito, e só com ponto de restauração criado antes.",
            metric="Latência de DPC do caminho de entrada",
        ),
        OptimizationTask(
            "usb_hub_power_off", "Impedir o Windows de desligar os hubs USB", MODULE["id"],
            "Input / USB", ("competitive", "campanha", "stream"),
            risk="low",
            description="A suspensão seletiva de USB é do plano de energia; está aqui é a permissão que "
                        "cada hub e controlador USB da placa-mãe carrega individualmente. É a segunda "
                        "metade do mesmo problema: o periférico que demora um instante para responder "
                        "depois de alguns segundos parado.",
            apply=lambda c, x: c.set_usb_hub_power_verified(False), verify=verify_usb_hubs,
            revert=revert_usb_hubs, compatible=compatible_usb_hubs,
            tags=("usb", "power", "motherboard"),
            source="EnhancedPowerManagementEnabled em HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB"
                   "\\<instância>\\Device Parameters — é a caixa 'O computador pode desligar este "
                   "dispositivo' da aba Gerenciamento de Energia de cada hub USB.",
            trade_off="Os controladores USB deixam de entrar em economia, o que consome alguns watts a "
                      "mais em repouso. Em notebook na bateria isso é perceptível ao longo do dia.",
            metric="Atraso do primeiro evento após o periférico ficar parado",
        ),
        OptimizationTask(
            "keyboard_repeat_fast", "Repetição de tecla no máximo", MODULE["id"], "Input / Teclado",
            ("competitive",),
            risk="low",
            description="Coloca o atraso de repetição no mínimo e a velocidade no máximo — os extremos que o "
                        "próprio painel de controle do Windows oferece.",
            apply=lambda c, x: c.set_keyboard_repeat_verified(0, 31), verify=verify_keyboard_repeat,
            revert=revert_keyboard_repeat, tags=("keyboard", "input", "registry"),
            source="Propriedades do Teclado (Painel de Controle): KeyboardDelay 0-3 e KeyboardSpeed 0-31, em "
                   "HKCU\\Control Panel\\Keyboard.",
            trade_off="Segurar uma tecla passa a repetir muito rápido, inclusive ao digitar texto. Quem "
                      "escreve bastante costuma preferir o padrão.",
            metric="",
        ),
        OptimizationTask(
            "usb_interrupts_ecores", "Interrupções do USB do controle nos núcleos E", MODULE["id"],
            "Input / USB", ("competitive",), risk="high", restart=True, automatic=False,
            description="Controle ou mouse em 4K/8K manda milhares de relatórios por segundo, e o Windows "
                        "entrega as interrupções da controladora USB num núcleo só — quase sempre um núcleo "
                        "P, o mesmo que o jogo usa. Isto manda as interrupções da controladora onde o "
                        "controle está conectado para os núcleos E.",
            apply=lambda c, x: c.set_usb_interrupts_on_ecores_verified(), verify=usbirq_verify,
            revert=lambda c, x: c.usb_interrupt_affinity_revert(), compatible=usbirq_compat,
            tags=("usb", "dpc", "input", "manual", "restart"),
            source="DevicePolicy = 4 (IrqPolicySpecifiedProcessors) e AssignmentSetOverride em ...\\Enum\\PCI"
                   "\\<controladora>\\Device Parameters\\Interrupt Management\\Affinity Policy — a mesma chave "
                   "que a Interrupt Affinity Policy Tool da Microsoft grava.",
            trade_off="Só vale depois de reiniciar, e muda também o teclado e o mouse que estiverem na mesma "
                      "controladora. Se algum dispositivo USB parar de responder, desfaça pelo AZOR ou pelo "
                      "ponto de restauração criado antes. Só existe em CPU híbrida (núcleos P e E).",
            metric="Interrupções e DPCs por segundo no núcleo que o jogo usa",
        ),
    ]
