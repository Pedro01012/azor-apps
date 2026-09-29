"""BOOST: o clique único que deixa o PC no máximo.

Ordem, e por quê:
  1. Mede o PC (processos, RAM, CPU) para o antes e depois.
  2. Tweaks do modo escolhido. O motor grava o backup antes do primeiro item,
     conserta o que outros otimizadores quebraram e relê cada ajuste.
     Sem backup confirmado, nada mais roda.
  3. Remove os apps inúteis (só os marcados como lixo de verdade).
  4. Tira do boot os programas inúteis (no Extremo, também os lançadores).
  5. Limpa temporários, cache de atualização e sobras de driver.
  6. Deixa o modo reaplicado a cada login (o Windows Update desfaz ajustes).
  7. Mede de novo e grava o relatório.
Cada etapa pode ser desligada na janela de confirmação.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional

from . import engine, debloat, startup, cleanup, presets, processes
from .policy import MODE_LABELS, USER_MODES

DEFAULTS = {"debloat": True, "startup": True, "processes": True, "cleanup": True, "keep_on_logon": True}


def run(core, mode: str, options: Optional[Dict[str, Any]] = None,
        progress: Optional[Callable[[str, str, str], None]] = None) -> Dict[str, Any]:
    mode = mode if mode in USER_MODES else "auto"
    opts = {**DEFAULTS, **{k: bool(v) for k, v in (options or {}).items() if k in DEFAULTS}}
    say = progress or (lambda *a: None)
    started = time.time()

    # O pré-set do hardware vale em todos os modos (protege o que esta peça não
    # aguenta); no Automático ele também escolhe a base e os itens a mais.
    say("Reconhecendo o PC", "reading", "Processador, placa de vídeo, memória, disco e formato.")
    try:
        preset = presets.resolve(core, mode, force=True)
        known = preset["memory"]["known"]
        say("Pré-set do PC", "completed", ("Reconhecido da memória do AZOR: " if known else "Novo PC: ") + preset["name"])
    except Exception as exc:
        preset = None
        say("Pré-set do PC", "failed", f"Hardware não reconhecido ({exc}); usando só as regras do modo.")
    base = (preset or {}).get("base") or ("agressivo" if mode == "auto" else mode)

    say("Medindo o PC", "reading", "Processos, RAM e CPU antes do BOOST.")
    try:
        before = core.system_sample()
    except Exception as exc:
        before = {"available": False, "detail": str(exc)}

    results = engine.execute(base, progress=say, preset=presets.engine_view(preset))
    backup = next((r for r in results if r.get("name") == "Backup / Restore"), {})
    if backup.get("status") != "completed":
        return {"ok": False, "mode": mode, "results": results,
                "detail": "O backup não foi confirmado, então nada foi alterado. " + str(backup.get("detail") or "")}

    tweaks = [r for r in results if r.get("id")]
    failed_items = [{"name": r.get("name"), "detail": r.get("detail")} for r in tweaks if r.get("status") == "failed"]
    summary: Dict[str, Any] = {
        "changed": sum(1 for r in tweaks if r.get("status") == "completed" and not r.get("already_applied")),
        "already": sum(1 for r in tweaks if r.get("status") == "completed" and r.get("already_applied")),
        "failed": len(failed_items), "failed_items": failed_items[:12],
        "restart": any(bool(r.get("restart")) for r in tweaks),
    }

    apps_out: Dict[str, Any] = {"removed": 0, "names": []}
    if opts["debloat"]:
        say("Apps inúteis", "applying", "Procurando apps que só ocupam espaço…")
        try:
            wanted = debloat.recommended_installed(core)
            if wanted:
                res = debloat.remove(core, wanted, progress=say)
                apps_out = {"removed": res.get("removed", 0),
                            "names": [r["name"] for r in res.get("results", []) if r.get("ok")]}
            else:
                say("Apps inúteis", "completed", "Nenhum app inútil instalado.")
        except Exception as exc:
            say("Apps inúteis", "failed", str(exc))

    startup_out: Dict[str, Any] = {"disabled": []}
    if opts["startup"]:
        try:
            extreme = bool((preset or {}).get("startup_extreme")) if preset else mode != "maximo"
            startup_out = startup.boost_disable(core, extreme=extreme, progress=say)
        except Exception as exc:
            say("Inicialização", "failed", str(exc))

    proc_out: Dict[str, Any] = {"closed": [], "freed_mb": 0}
    if opts["processes"]:
        try:
            proc_out = processes.close_useless(core, progress=say)
        except Exception as exc:
            say("Processos inúteis", "failed", str(exc))

    cleanup_out: Dict[str, Any] = {"freed_mb": 0}
    if opts["cleanup"]:
        try:
            cleanup_out = cleanup.clean(core, cleanup.boost_ids(), progress=say)
        except Exception as exc:
            say("Limpeza", "failed", str(exc))

    logon: Dict[str, Any] = {"ok": None}
    if opts["keep_on_logon"] and core.is_admin():
        try:
            import azor_autostart
            logon = azor_autostart.install(core, mode, say)
        except Exception as exc:
            logon = {"ok": False, "detail": str(exc)}

    say("Medindo o PC", "reading", "Mesma medição, depois do BOOST.")
    try:
        after = core.system_sample()
    except Exception as exc:
        after = {"available": False, "detail": str(exc)}

    report_id = str(uuid.uuid4())
    report = {
        "version": 2, "id": report_id, "time": time.time(), "duration_s": round(time.time() - started, 1),
        "mode": mode, "mode_label": MODE_LABELS.get(mode, mode), "ok": not failed_items,
        "restart": summary["restart"],
        "preset": ({"name": preset["name"], "key": preset["key"], "skip": len(preset["skip"]), "add": len(preset["add"]),
                    "notes": [n["title"] for n in preset["notes"]]} if preset else None),
        "processes": proc_out,
        "tweaks": summary, "apps": apps_out,
        "startup": {"disabled": startup_out.get("disabled", [])},
        "cleanup": {"freed_mb": cleanup_out.get("freed_mb", 0)},
        "logon": {"ok": logon.get("ok"), "detail": logon.get("detail")},
        "before": before, "after": after,
        "comparison": core.compare_system_samples(before, after),
        "results": results,
    }
    report["detail"] = (
        f"{summary['changed']} ajuste(s) novo(s), {summary['already']} já estavam no lugar"
        + (f", {apps_out['removed']} app(s) removido(s)" if apps_out["removed"] else "")
        + (f", {len(report['startup']['disabled'])} programa(s) fora do boot" if report["startup"]["disabled"] else "")
        + (f", {len(proc_out['closed'])} processo(s) inútil(eis) fechado(s)" if proc_out.get("closed") else "")
        + (f", {report['cleanup']['freed_mb']:.0f} MB liberados" if report["cleanup"]["freed_mb"] else "")
        + (f", {summary['failed']} falha(s)" if summary["failed"] else "") + "."
    )
    try:
        from .transactions import save
        save(core.DATA_DIR / "reports" / (report_id + ".json"), report)
        report["report_id"] = report_id
    except Exception as exc:
        report["report_error"] = str(exc)
    settings = core.load_settings()
    settings["performance_mode"] = mode
    settings["last_boost"] = {"time": report["time"], "mode": mode, "report_id": report.get("report_id"),
                              "detail": report["detail"]}
    core.save_settings(settings)
    if preset:
        presets.remember(core, preset, applied=True)
    core.journal("boost", mode=mode, report_id=report_id, changed=summary["changed"], failed=summary["failed"],
                 preset=(preset or {}).get("key"))
    return report
