from __future__ import annotations

from .base import OptimizationTask

MODULE = {
    "id": "maintenance",
    "label": "Armazenamento",
    "description": "Limpeza conservadora e mensurável; não toca em Downloads, saves, drivers ou arquivos do jogo.",
    "automatic": True,
}


def tasks():
    def compatible(core, ctx):
        gm = core.game_monitor_snapshot()
        if gm.get("running") or gm.get("maintenance_blockers"):
            return False, "Jogo/live detectado; limpeza adiada para não competir por I/O durante a sessão."
        return True, "Nenhum jogo/live bloqueando a manutenção segura."

    def apply(core, ctx):
        result = core.daily_maintenance(force=False)
        ok = bool(result.get("ok"))
        detail = str(result.get("detail") or "")
        # No stale temp entries is a valid no-op, not a failure.
        if not ok and not core.scan_safe_cleanup(48).get("items"):
            return True, detail or "Nenhum temporário antigo elegível para limpeza."
        return ok, detail

    # Sem revert: apagar arquivo é a única coisa nesta lista que não volta atrás.
    # Marcar como reversível seria mentira, então o motor declara reversible=False
    # e a UI mostra isso antes de aplicar.
    return [OptimizationTask(
        "safe_cleanup", "Limpeza segura de temporários", MODULE["id"], "Armazenamento / TEMP", ("safe", "competitive", "campanha", "stream"),
        reversible=False,
        description="Remove apenas TEMP antigo dentro da política segura atual.", apply=apply, compatible=compatible,
        tags=("storage", "cleanup"),
        source="Pasta %TEMP% do usuário, com corte por idade de arquivo. Não usa cleanmgr nem toca em Downloads, "
               "perfis de jogo, shader cache atual ou pontos de restauração.",
        trade_off="Não é reversível: arquivo apagado não volta. Em compensação, só entram temporários mais velhos "
                  "que o corte de horas, e nunca arquivos abertos por um processo.",
        metric="Espaço livre no disco do sistema",
    )]
