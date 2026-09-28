from __future__ import annotations

from .base import OptimizationTask
from .power_policy import POWER_EXPECTED

MODULE = {
    "id": "power",
    "label": "Energia",
    "description": "AZOR DESEMPENHO, baseado no Alto desempenho, com política AC de CPU verificada e valores originais guardados.",
    "automatic": True,
}


def tasks():
    def compatible(core, ctx):
        battery=bool(ctx.get("hardware", {}).get("battery"))
        if battery:
            return True, "Notebook: opção manual, índices AC moderados; valores DC preservados. Considere consumo e temperatura."
        return True, "AZOR DESEMPENHO pode ser criado a partir do Alto desempenho e verificado neste PC."

    def apply(core, ctx):
        return core.set_azor_fps_boost_power()

    def verify(core, ctx):
        status = core.azor_fps_boost_power_status()
        checks = [status.get("active") is True]
        checks.extend(status.get(key) in (None, wanted) for key, wanted in POWER_EXPECTED.items())
        ok=all(checks)
        return ok, (f"AZOR FPS BOOST confirmado; GUID ativo {status.get('active_guid')}." if ok else f"AZOR FPS BOOST não foi totalmente confirmado: {status}")

    def revert(core, ctx):
        """Volta ao esquema que estava ativo antes do AZOR.

        O plano AZOR não é apagado: ele é do app, não do usuário, e deixá-lo
        existir sem estar ativo não muda nada no comportamento do Windows.
        """
        original = str(core.baseline_state().get("power_scheme") or "")
        if not original:
            return False, "O baseline não registrou qual era o plano de energia anterior; nada foi alterado."
        p = core.run_hidden(["powercfg", "/setactive", original], timeout=8)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "O Windows recusou a troca de plano.").strip()
        active = (core.get_active_power_scheme() or "").lower()
        ok = active == original.lower()
        core.journal("revert_power_plan", requested=original, active=active, ok=ok)
        return ok, (f"Plano de energia anterior reativado e verificado ({original})." if ok
                    else f"A troca foi solicitada, mas o Windows continua com {active or 'desconhecido'}.")

    def idle_compat(core, ctx):
        if ctx.get("hardware", {}).get("battery"):
            return False, ("Notebook detectado. Impedir a CPU de entrar em estado ocioso derrete a "
                           "autonomia e esquenta o aparelho fechado; o AZOR não oferece isso aqui.")
        state = core.processor_idle_state()
        if not state.get("readable") and not state.get("hidden"):
            return False, state.get("detail") or "IDLEDISABLE não está exposto neste PC."
        if state.get("hidden") and not core.is_admin():
            return False, (state.get("detail") or "") + " Revelar exige o AZOR como administrador."
        if state.get("disabled"):
            return False, "Os estados ociosos da CPU já estão desligados no plano ativo."
        if not core.is_admin():
            return False, ("Desktop na tomada e o powercfg expõe o índice, mas alterar estados "
                           "ociosos exige o AZOR aberto como administrador.")
        return True, "Desktop na tomada, e o powercfg expõe o índice."

    def idle_verify(core, ctx):
        state = core.processor_idle_state()
        ok = bool(state.get("disabled"))
        return ok, ("powercfg relido: a CPU não entra mais em estado ocioso no plano ativo." if ok
                    else f"O powercfg ainda reporta IDLEDISABLE={state.get('ac')}.")

    def idle_revert(core, ctx):
        return core.set_processor_idle_disabled(False)

    def nvme_compat(core, ctx):
        state = core.nvme_idle_state()
        if state.get("never"):
            return False, "O NVMe j\u00e1 est\u00e1 configurado para nunca entrar em baixa energia."
        if not state.get("readable") and not state.get("hidden"):
            return False, state.get("detail") or "Este PC n\u00e3o exp\u00f5e o tempo de inatividade do NVMe."
        if not core.is_admin():
            return False, ((state.get("detail") or "") + " Alterar exige o AZOR como administrador.").strip()
        return True, ("O NVMe entra em estado de baixa energia quando fica parado, e acordar custa "
                      "tempo no primeiro acesso seguinte \u2014 que costuma ser exatamente o "
                      "carregamento de textura no meio da partida.")

    def nvme_verify(core, ctx):
        state = core.nvme_idle_state()
        ok = bool(state.get("never"))
        return ok, ("powercfg relido: o NVMe n\u00e3o entra mais em baixa energia no plano ativo." if ok
                    else f"O powercfg ainda reporta {state.get('ac')}.")

    def nvme_revert(core, ctx):
        saved = core.baseline_state().get("nvme_idle") or {}
        if not isinstance(saved.get("ac"), int):
            return False, "O baseline n\u00e3o registrou o tempo anterior de inatividade do NVMe."
        return core.set_nvme_idle_never_verified(False)

    nvme_task, idle_task, plan_task = [OptimizationTask(
        "nvme_idle_never", "Impedir o SSD NVMe de entrar em baixa energia", MODULE["id"],
        "Energia / Disco", ("competitive",), risk="medium",
        description="O NVMe desliga partes de si quando fica parado alguns milissegundos, e voltar "
                    "custa tempo. Em jogo isso aparece como travadinha no carregamento de textura "
                    "depois de um trecho sem I/O.",
        apply=lambda c, x: c.set_nvme_idle_never_verified(True), verify=nvme_verify,
        revert=nvme_revert, compatible=nvme_compat, tags=("ssd", "latency", "power"),
        source="Tempo limite de inatividade do NVMe (subgrupo de disco do powercfg). Vem oculto nas "
               "op\u00e7\u00f5es de energia; o AZOR revela o atributo ao aplicar.",
        trade_off="O SSD consome um pouco mais em repouso e esquenta mais. Em notebook na bateria "
                  "isso aparece na autonomia; em desktop, quase nada.",
        metric="Travadinhas no primeiro acesso ao disco",
    ), OptimizationTask(
        "processor_idle_disable", "Impedir a CPU de entrar em estado ocioso", MODULE["id"],
        "Energia / CPU", ("competitive",), risk="high", automatic=False,
        description="Os estados C da CPU economizam energia parando núcleos, e sair deles custa tempo "
                    "— é uma das fontes reais de latência que sobra depois que o plano de energia já "
                    "está no máximo. Desligados, a CPU responde na hora, sempre.",
        apply=lambda c, x: c.set_processor_idle_disabled(True), verify=idle_verify,
        revert=idle_revert, compatible=idle_compat, tags=("cpu", "latency", "manual"),
        source="powercfg SUB_PROCESSOR IDLEDISABLE — opção de processador do esquema de energia, "
               "documentada nas opções de linha de comando do powercfg (Microsoft Learn).",
        trade_off="A CPU passa a consumir perto do máximo o tempo todo, mesmo com o PC parado: "
                  "temperatura mais alta, ventoinha audível e conta de luz maior. Em máquina com "
                  "refrigeração no limite, isso pode REDUZIR o desempenho por calor — o oposto do "
                  "pretendido. E com todos os núcleos sempre ativos o turbo cai para o de todos os "
                  "núcleos: medido num i5-13400F, 4,08 GHz em vez de até 4,6 GHz, justo na thread que "
                  "limita o jogo. Por isso é alto risco, fora do clique único e só em desktop.",
        metric="Latência de DPC/ISR e 1% low",
    ), OptimizationTask(
        "power_plan", "AZOR DESEMPENHO", MODULE["id"], "Windows / Energia", ("safe", "competitive", "campanha", "stream"),
        risk="medium", description="Plano baseado no Alto desempenho: CPU mínima 5%, máxima 100%, boost agressivo, preferência de desempenho (EPP 0) e resfriamento ativo quando suportados. Preserva USB, PCIe, disco e estacionamento de núcleos.",
        apply=apply, verify=verify, revert=revert, compatible=compatible, tags=("powercfg", "azor-fps-boost", "verified"),
        source="powercfg — Microsoft Learn (Alto desempenho e-9a42b02..., SUB_PROCESSOR, SUB_PCIEXPRESS, USB 2a737441…, SUB_DISK): "
               "https://learn.microsoft.com/windows-hardware/design/device-experiences/powercfg-command-line-options",
        trade_off="Consumo e temperatura dependem da carga. Não força CPU mínima em 100% nem desativa repouso. "
                  "Em notebook, só os índices de tomada (AC) são alterados; na bateria o plano mantém os valores herdados.",
        metric="Clock sustentado sob carga e 1% low",
    )]
    # O plano vem primeiro: os dois ajustes acima gravam no plano ATIVO, e o AZOR
    # DESEMPENHO troca o plano ativo. Na ordem antiga eles eram gravados num plano
    # que deixava de valer logo em seguida.
    return [plan_task, nvme_task, idle_task]
