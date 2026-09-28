from __future__ import annotations

from .base import OptimizationTask

MODULE = {
    "id": "memory",
    "label": "RAM & Memória",
    "description": "Mantém paginação segura quando necessário; XMP/EXPO e timings continuam fora da automação do Windows.",
    "automatic": True,
}


def tasks():
    def compatible(core, ctx):
        state=core.get_automatic_pagefile()
        if state is True:
            return False, "Paginação automática já está ativa; nenhuma mudança necessária."
        if state is False:
            return True, "Paginação automática está desativada; restaurar o gerenciamento do Windows reduz risco de falta de memória/stutter."
        return False, "Estado da paginação não pôde ser confirmado; preservado."

    def verify(core, ctx):
        ok=core.get_automatic_pagefile() is True
        return ok, "Paginação automática relida como ativa." if ok else "Paginação automática não foi confirmada."

    def revert(core, ctx):
        original = core.baseline_state().get("automatic_pagefile")
        if not isinstance(original, bool):
            return False, "O baseline não registrou o estado anterior da paginação; nada foi alterado."
        ok, detail = core.set_automatic_pagefile_verified(original)
        core.journal("revert_pagefile", requested=original, ok=ok)
        return ok, detail

    def compression_compat(core, ctx):
        ram = float(ctx.get("hardware", {}).get("ram_gb") or 0)
        if ram < 32:
            return False, (f"Com {ram:g} GB de RAM, a compressão paga por si: ela evita paginação, que "
                           "custa muito mais caro que o trabalho de CPU dela. O AZOR só oferece "
                           "desligar a partir de 32 GB.")
        state = core.memory_compression_state()
        if not state.get("readable"):
            return False, "O Get-MMAgent não respondeu o estado da compressão; preservado."
        if state.get("enabled") is False:
            return False, "A compressão de memória já está desligada."
        found = f"{ram:g} GB de RAM: há memória suficiente para testar sem a compressão."
        if not core.is_admin():
            return False, found + " O ajuste exige o AZOR aberto como administrador."
        return True, found

    def compression_verify(core, ctx):
        state = core.memory_compression_state(force=True)
        ok = state.get("enabled") is False
        return ok, ("Get-MMAgent relido: compressão de memória desligada." if ok
                    else f"O Windows ainda reporta compressão = {state.get('enabled')}.")

    def compression_revert(core, ctx):
        saved = core.baseline_state().get("memory_compression") or {}
        original = saved.get("enabled")
        if not isinstance(original, bool):
            return False, "O baseline não registrou o estado anterior da compressão de memória."
        return core.set_memory_compression_verified(original)

    return [OptimizationTask(
        "memory_compression_off", "Testar o PC sem a compressão de memória", MODULE["id"],
        "RAM / Compressão", ("competitive",), risk="experimental", automatic=False,
        description="O Windows comprime páginas de memória para caber mais na RAM, gastando CPU para "
                    "isso. Com 32 GB ou mais, sobra memória e o trabalho de compressão vira custo puro "
                    "— mas o ganho varia por jogo, então este item é um teste A/B seu: aplique, jogue "
                    "duas partidas e reverta se não sentir diferença.",
        apply=lambda c, x: c.set_memory_compression_verified(False), verify=compression_verify,
        revert=compression_revert, compatible=compression_compat,
        tags=("memory", "cpu", "ab-test"),
        source="Enable-MMAgent / Disable-MMAgent -mc — módulo MMAgent do PowerShell, documentado pela "
               "Microsoft. O estado é lido de volta por Get-MMAgent.",
        trade_off="Sem compressão, o mesmo conjunto de programas ocupa mais RAM física. Se a memória "
                  "encher, o Windows volta a paginar em disco — que é bem pior que comprimir. Por isso "
                  "o corte de 32 GB, e por isso o AZOR não promete ganho aqui.",
        metric="Uso de CPU em repouso e p99 de frametime",
    ), OptimizationTask(
        "automatic_pagefile", "Devolver a paginação ao Windows", MODULE["id"], "RAM / Paginação", ("safe","competitive","campanha","stream"),
        risk="low", restart=True, description="Se a paginação estiver desativada, volta para o gerenciamento automático e verifica o estado.",
        apply=lambda c,x:c.set_automatic_pagefile_verified(True), verify=verify, revert=revert, compatible=compatible,
        tags=("memory","pagefile","stutter"),
        source="Win32_ComputerSystem.AutomaticManagedPagefile — o mesmo que a caixa 'Gerenciar automaticamente o "
               "tamanho do arquivo de paginação' em Opções de Desempenho.",
        trade_off="Ocupa espaço em disco. Em troca, o jogo não é encerrado por falta de memória de commit — "
                  "o desligamento do pagefile é uma das causas mais comuns de travamento atribuído ao jogo.",
        metric="Stutter por paginação (picos de frametime)",
    )]
