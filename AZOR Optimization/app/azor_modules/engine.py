from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
from time import perf_counter
from dataclasses import replace

from .base import OptimizationTask, PROFILES, PROFILE_LABELS, RISK_LABELS, normalize_result
from . import ENGINE_NAME
from . import policy
from . import (registry, power, gpu, fortnite, network, input_usb, hardware,
               services, memory, system, storage, repair, lite, prefs, gamer)

# A ordem importa: e a ordem em que o lote aplica. Nucleo e energia primeiro,
# porque os dois mudam como o Windows agenda tudo o que vem depois; limpeza por
# ultimo, porque ela e a unica que disputa I/O.
# Reparo vem primeiro: nao adianta otimizar em cima de um Windows que outro
# programa quebrou. Religar o firewall e a Protecao do Sistema antes de mexer
# em qualquer coisa tambem garante a rede de seguranca do resto do lote.
MODULES = (repair, registry, system, power, gpu, memory, input_usb, network, storage,
           services, lite, prefs, fortnite, hardware)


def _core():
    import azor_core as core
    return core


def _all_tasks() -> List[OptimizationTask]:
    out: List[OptimizationTask] = []
    ids = set()
    for module in MODULES:
        for task in module.tasks():
            if task.id in ids:
                raise RuntimeError(f"Duplicate optimization task id: {task.id}")
            ids.add(task.id)
            keys = tuple(getattr(module, 'KEYS', {}).get(task.id, ()))
            if keys and not task.registry_keys:
                task = replace(task, registry_keys=keys)
            out.append(policy.review(task))
    return out


def _context(core, requested_profile: str, preset: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from azor_managers import WindowsDetection
    hp = core.hardware_profile()
    requested = str(requested_profile or "auto").lower()
    resolved = str(hp.get("recommended") or "safe").lower() if requested == "auto" else requested
    if resolved not in set(PROFILES):
        resolved = "safe"
    try:
        streamer = bool(core.load_settings().get("streamer"))
    except Exception:
        streamer = False
    return {
        "requested_profile": requested,
        "resolved_profile": resolved,
        "hardware": hp,
        "fortnite": core.detect_fortnite(),
        "windows":WindowsDetection.read(),
        "streamer": streamer,
        "preset": preset,
    }


def module_manifest() -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for task in _all_tasks():
        counts[task.module] = counts.get(task.module, 0) + 1
    out = []
    for module in MODULES:
        meta = dict(module.MODULE)
        meta["task_count"] = counts.get(meta["id"], 0)
        out.append(meta)
    return out


def build_plan(requested_profile: str = "auto") -> Dict[str, Any]:
    core = _core()
    ctx = _context(core, requested_profile)
    plan = []
    for task in _all_tasks():
        eligible = bool(task.apply) and task.supports_profile(ctx["resolved_profile"])
        reason = "Compatível com o perfil selecionado." if eligible else f"Não faz parte do perfil {PROFILE_LABELS.get(ctx['resolved_profile'], ctx['resolved_profile'].upper())}."
        if eligible and task.compatible:
            try:
                eligible, reason = task.compatible(core, ctx)
            except Exception as exc:
                eligible, reason = False, f"Falha ao validar compatibilidade: {exc}"
        plan.append({
            "id": task.id, "name": task.name, "module": task.module, "category": task.category,
            "risk": task.risk, "risk_label": RISK_LABELS.get(task.risk, task.risk),
            "reversible": bool(task.reversible), "can_revert": task.can_revert(),
            "restart": task.restart,
            "automatic": task.automatic, "eligible": bool(eligible), "reason": str(reason),
            "description": task.description, "profiles": list(task.profiles), "tags": list(task.tags),
            "source": task.source, "trade_off": task.trade_off, "metric": task.metric,
            "classification":task.classification,"disposition":task.disposition,"audit_reason":task.audit_reason,
            "requires_admin":task.requires_admin,"can_apply":bool(task.apply),
        })
    return {
        "engine": ENGINE_NAME,
        "profiles": list(PROFILES),
        "profile_labels": dict(PROFILE_LABELS),
        "requested_profile": ctx["requested_profile"],
        "resolved_profile": ctx["resolved_profile"],
        "hardware_profile": ctx["hardware"],
        "modules": module_manifest(),
        "tasks": plan,
        "eligible_count": sum(1 for x in plan if x["eligible"]),
        "skipped_count": sum(1 for x in plan if not x["eligible"]),
    }


def engine_status(requested_profile: str = "auto") -> Dict[str, Any]:
    try:
        plan = build_plan(requested_profile)
        return {
            "ok": True, "name": ENGINE_NAME, "resolved_profile": plan["resolved_profile"],
            "eligible_count": plan["eligible_count"], "skipped_count": plan["skipped_count"],
            "modules": plan["modules"],
        }
    except Exception as exc:
        return {"ok": False, "name": ENGINE_NAME, "reason": str(exc), "modules": []}


# Um catalogo de trinta tweaks nao cabe numa cadeia de if/elif por id: o proximo
# tweak adicionado ficaria sem estado na tela e ninguem notaria. Agora o estado
# vem de quem ja sabe responder - a propria funcao verify() do tweak, que e a
# mesma usada para confirmar a aplicacao. Uma fonte de verdade, nao duas.
def _current_state(core, task: OptimizationTask, ctx: Dict[str, Any]) -> Dict[str, Any]:
    if task.verify is None:
        return {"status": None, "current": "Sem releitura", "detail": ""}
    try:
        ok, detail = normalize_result(task.verify(core, ctx))
    except Exception as exc:
        return {"status": None, "current": "Não confirmado", "detail": f"Estado não pode ser lido: {exc}"}
    return {"status": "applied" if ok else "recommended",
            "current": "Aplicado" if ok else "Pendente", "detail": detail}


def _analysis_for_task(core, task: OptimizationTask, ctx: Dict[str, Any], eligible: bool, reason: str) -> Dict[str, Any]:
    base = {
        "id": task.id, "name": task.name, "module": task.module, "category": task.category,
        "risk": task.risk, "risk_label": RISK_LABELS.get(task.risk, task.risk),
        "recommended": "Aplicar" if eligible else "Preservar",
        "current": "Detectado", "status": "recommended" if eligible else "not_applicable",
        "detail": reason if not eligible else task.description,
        "reversible": bool(task.reversible), "can_revert": task.can_revert(),
        "source": task.source, "trade_off": task.trade_off, "metric": task.metric,
        "restart": task.restart,
        "classification":task.classification,"disposition":task.disposition,"requires_admin":task.requires_admin,
    }
    if eligible:
        state = _current_state(core, task, ctx)
        if state["status"]:
            base["status"] = state["status"]
            base["current"] = state["current"]
            base["detail"] = state["detail"] or base["detail"]
        elif state["detail"]:
            base["status"] = "optional"
            base["detail"] = state["detail"]
    try:
        if task.id == "game_mode":
            applied = bool(core.verify_game_mode()); base.update(current="On" if applied else "Off/unknown", status="applied" if applied else base["status"])
        elif task.id == "game_dvr":
            applied = bool(core.verify_game_dvr_off()); base.update(current="Off" if applied else "On/unknown", status="applied" if applied else base["status"])
        elif task.id == "windows_suggestions":
            applied = bool(core.verify_windows_suggestions_off()); base.update(current="Off" if applied else "On/unknown", status="applied" if applied else base["status"])
        elif task.id == "transparency":
            applied = bool(core.verify_transparency_off()); base.update(current="Off" if applied else "On/unknown", status="applied" if applied else base["status"])
        elif task.id == "widgets":
            applied = bool(core.verify_widgets_hidden()); base.update(current="Hidden" if applied else "Visible/unknown", status="applied" if applied else base["status"])
        elif task.id == "power_plan":
            base["current"] = str(core.get_active_power_scheme() or "unknown")
        elif task.id == "fortnite_gpu":
            base["current"] = "Fortnite detectado" if ctx.get("fortnite", {}).get("exe") else "Fortnite não detectado"
    except Exception as exc:
        base["status"] = "optional"
        base["detail"] = f"Estado não pôde ser confirmado: {exc}"
    if not eligible:
        base["status"] = "not_applicable"
    elif not policy.automatic_decision(task,ctx)[0] and base["status"] == "recommended":
        base["status"] = "optional"
        base["detail"] = policy.automatic_decision(task,ctx)[1]
    return base


def analyze(requested_profile: str = "auto") -> List[Dict[str, Any]]:
    core = _core()
    ctx = _context(core, requested_profile)
    items: List[Dict[str, Any]] = []
    for task in _all_tasks():
        eligible = bool(task.apply) and task.supports_profile(ctx["resolved_profile"])
        reason = "Compatível com o perfil selecionado."
        if not eligible:
            reason = f"Preservado pelo perfil {PROFILE_LABELS.get(ctx['resolved_profile'], ctx['resolved_profile'].upper())}."
        elif task.compatible:
            try:
                eligible, reason = task.compatible(core, ctx)
            except Exception as exc:
                eligible, reason = False, f"Compatibilidade não confirmada: {exc}"
        items.append(_analysis_for_task(core, task, ctx, bool(eligible), str(reason)))
    return items


def simulate(requested_profile: str = "competitive") -> Dict[str, Any]:
    """Mostra exatamente o que o lote faria, sem tocar em nada.

    Roda toda a etapa de decisao real - perfil resolvido, compatibilidade, motivo
    de exclusao - e para antes do primeiro apply. E o único modo em que o AZOR
    responde "o que você faria no meu PC?" sem já ter feito.
    """
    core = _core()
    ctx = _context(core, requested_profile)
    steps: List[Dict[str, Any]] = []
    for task in _all_tasks():
        row = {"id": task.id, "name": task.name, "module": task.module, "risk": task.risk,
               "risk_label": RISK_LABELS.get(task.risk, task.risk), "restart": task.restart,
               "reversible": bool(task.reversible), "can_revert": task.can_revert(),
               "source": task.source, "trade_off": task.trade_off, "metric": task.metric}
        if not task.supports_profile(ctx["resolved_profile"]):
            row.update(action="skip", detail=f"Preservado pelo perfil {PROFILE_LABELS.get(ctx['resolved_profile'], ctx['resolved_profile'].upper())}.")
            steps.append(row); continue
        if task.compatible:
            try:
                eligible, detail = task.compatible(core, ctx)
            except Exception as exc:
                eligible, detail = False, f"Falha ao validar compatibilidade: {exc}"
            if not eligible:
                row.update(action="skip", detail=detail); steps.append(row); continue
        # Mesma decisao do lote real: a simulacao nao pode prometer mais nem menos.
        automatic, reason = policy.automatic_decision(task, ctx) if task.apply is not None else (False, "")
        if not automatic:
            row.update(action="manual", detail=reason or "Depende do hardware ou da preferencia do usuário; fica como acao manual.")
            steps.append(row); continue
        row.update(action="apply", detail=task.description)
        steps.append(row)
    would_apply = [s for s in steps if s["action"] == "apply"]
    core.journal("simulation", profile=ctx["resolved_profile"], would_apply=[s["id"] for s in would_apply])
    return {
        "ok": True, "simulated": True, "resolved_profile": ctx["resolved_profile"],
        "requested_profile": ctx["requested_profile"],
        "steps": steps,
        "apply_count": len(would_apply),
        "skip_count": sum(1 for s in steps if s["action"] == "skip"),
        "manual_count": sum(1 for s in steps if s["action"] == "manual"),
        "restart_count": sum(1 for s in would_apply if s.get("restart")),
        "irreversible": [s["id"] for s in would_apply if not s.get("reversible")],
        "note": "Nada foi alterado. Esta e a lista exata do que o botão Aplicar faria agora, neste PC.",
    }


def arsenal(requested_profile: str = "auto", preset: Optional[Dict[str, Any]] = None,
            batch_profile: str = "maximo") -> Dict[str, Any]:
    """Plano e estado atual numa varredura única.

    Antes a tela do Arsenal chamava build_plan() e analyze() em sequencia, e as
    duas rodavam o `compatible` de todos os tweaks -- o mesmo trabalho duas vezes,
    inclusive as leituras que abrem processo. Aqui cada tweak e visitado uma vez:
    compat uma vez, verify uma vez.
    """
    core = _core()
    ctx = _context(core, requested_profile)
    profile_label = PROFILE_LABELS.get(ctx["resolved_profile"], ctx["resolved_profile"].upper())
    rows: List[Dict[str, Any]] = []
    for task in _all_tasks():
        eligible = bool(task.apply) and task.supports_profile(ctx["resolved_profile"])
        reason = "Compativel com o perfil selecionado."
        if not eligible:
            reason = f"Preservado pelo perfil {profile_label}."
        elif task.compatible:
            try:
                eligible, reason = task.compatible(core, ctx)
            except Exception as exc:
                eligible, reason = False, f"Compatibilidade não confirmada: {exc}"
        state, current, detail = "not_applicable", "", ""
        if eligible:
            probe = _current_state(core, task, ctx)
            state = probe["status"] or "unknown"
            current, detail = probe["current"], probe["detail"]
        elif (task.apply is not None and task.can_revert() and task.verify is not None
              and task.supports_profile(ctx["resolved_profile"])
              and (" já " in f" {str(reason).lower()} " or "administrador" in str(reason).lower())):
            # "Já está desligado" e "exige administrador" chegam aqui como
            # incompatíveis. Sem reler, o item aplicado aparecia como "não se
            # aplica" e ficava sem o botão DESFAZER - o CPU sem repouso, por exemplo.
            probe = _current_state(core, task, ctx)
            if probe["status"] == "applied":
                state, current, detail = "applied", probe["current"], probe["detail"]
        rows.append({
            "id": task.id, "name": task.name, "module": task.module, "category": task.category,
            "risk": task.risk, "risk_label": RISK_LABELS.get(task.risk, task.risk),
            "reversible": bool(task.reversible), "can_revert": task.can_revert(),
            "restart": task.restart, "automatic": task.automatic,
            "can_apply":bool(task.apply),"classification":task.classification,"disposition":task.disposition,
            "audit_reason":task.audit_reason,"requires_admin":task.requires_admin,
            "eligible": bool(eligible), "reason": str(reason),
            "description": task.description, "profiles": list(task.profiles), "tags": list(task.tags),
            "source": task.source, "trade_off": task.trade_off, "metric": task.metric,
            "state": state, "current": current, "state_detail": detail,
            "relations": [dict(r) for r in (task.relations or ())],
            **_gamer_fields(task),
            **_batch_fields(task.id, batch_profile, preset),
        })
    # As relacoes so ajudam se o usuario vir o NOME e o ESTADO do outro item; um id
    # cru na tela nao diz nada a quem nao leu o codigo.
    by_id = {r["id"]: r for r in rows}
    for row in rows:
        for rel in row.get("relations") or []:
            other = by_id.get(rel.get("id"))
            if other:
                rel["name"] = other["name"]
                rel["applied"] = other["state"] == "applied"
                rel["eligible"] = other["eligible"]
    repairs = [r for r in rows if r["module"] == "repair"]
    return {
        "engine": ENGINE_NAME,
        "profiles": list(PROFILES), "profile_labels": dict(PROFILE_LABELS),
        "requested_profile": ctx["requested_profile"], "resolved_profile": ctx["resolved_profile"],
        "hardware_profile": ctx["hardware"], "modules": module_manifest(),
        "tasks": rows,
        "eligible_count": sum(1 for r in rows if r["eligible"]),
        "skipped_count": sum(1 for r in rows if not r["eligible"]),
        # O bloco de reparo e a historia mais forte da tela: "achamos N coisas que
        # outro programa quebrou". Ele so aparece quando N > 0.
        "repair": {
            "total": len(repairs),
            "found": [{"id": r["id"], "name": r["name"], "detail": r["reason"]}
                      for r in repairs if r["eligible"]],
            "unreadable": [{"id": r["id"], "name": r["name"], "detail": r["reason"]}
                           for r in repairs if not r["eligible"] and "administrador" in r["reason"]],
        },
    }


def _batch_fields(task_id: str, batch_profile: str, preset: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Se o BOOST de agora pega este item, e o que o pré-set do PC diz dele."""
    selected, why = policy.in_batch(task_id, batch_profile, preset)
    preset = preset or {}
    mark = ("skip" if task_id in (preset.get("skip") or {}) else
            "add" if task_id in (preset.get("add") or {}) else None)
    return {"in_boost": bool(selected), "preset": mark, "preset_reason": why if mark else ""}


def _gamer_fields(task: OptimizationTask) -> Dict[str, Any]:
    info = gamer.meta(task.id)
    boost = ("recomendado" if task.id in policy.RECOMENDADO else
             "extremo" if task.id in policy.EXTREMO else None)
    return {**info, "boost": boost, "one_way": task.id in policy.ONE_WAY,
            "ab_test": task.id in policy.AB_TEST_ONLY}


def _run_baseline_backed(core, task, ctx):
    """Ajuste sem captura transacional própria, liberado so nos modos Maximo/Agressivo.

    O lote grava o baseline antes do primeiro item, e a reversao do ajuste le de la.
    Falha na aplicação ou na releitura desfaz na hora pelo mesmo caminho.
    """
    rollback = None
    try:
        ok, detail = normalize_result(task.apply(core, ctx))
        if ok:
            ok, verified = normalize_result(task.verify(core, ctx))
            detail = verified or detail
    except Exception as exc:
        ok, detail = False, str(exc)
    if not ok:
        try:
            restored, r_detail = normalize_result(task.revert(core, ctx))
            rollback = {"ok": restored, "detail": r_detail}
        except Exception as exc:
            rollback = {"ok": False, "detail": str(exc)}
    core.journal("baseline_backed_apply", id=task.id, ok=ok, rollback=rollback)
    return {"ok": ok, "detail": detail, "transaction_id": None, "rollback": rollback}


def _run_repair(core, task, ctx):
    """Conserto do módulo Reparo: aplica e rele, sem rollback de proposito.

    Desfazer um conserto seria desligar de novo o firewall ou o TRIM. O que o
    protege e a releitura: sem ela confirmada, o item conta como falha e aparece
    para revisar em vez de entrar no resumo como feito.
    """
    try:
        ok, detail = normalize_result(task.apply(core, ctx))
        if ok:
            ok, verified = normalize_result(task.verify(core, ctx))
            detail = verified or detail
    except Exception as exc:
        ok, detail = False, str(exc)
    core.journal("repair_apply", id=task.id, ok=ok, detail=detail)
    return {"ok": ok, "detail": detail, "transaction_id": None, "rollback": None, "repair": True}


def _run_one(core, task, ctx, progress=None):
    from . import transactions
    if task.apply is None:
        return {"ok":False,"id":task.id,"detail":task.audit_reason or "Este ajuste foi retirado da aplicação."}
    windows=ctx.get('windows')
    if windows and (not windows.get('supported') or windows.get('build',0)<task.min_windows_build):
        return {"ok":False,"id":task.id,"detail":"WINDOWS_BUILD_UNSUPPORTED: nenhuma alteração iniciada."}
    if task.verify is None:
        return {"ok": False, "id": task.id, "name": task.name, "detail": "Ação sem verificação: não iniciada."}
    if "declarative" in task.tags or "registry" in task.tags or task.id in ("power_plan", "automatic_pagefile", "usb_suspend_off"):
        try:
            current, detail = normalize_result(task.verify(core, ctx))
        except Exception:
            current = False
        if current:
            core.mark_task_applied(task.id, task.name, ctx["resolved_profile"])
            return {"ok": True, "id": task.id, "name": task.name, "already_applied": True,
                    "restart": False, "detail": "Já configurado: estado relido; nenhuma alteração necessária."}
    baseline_backed = repair = False
    if not transactions.supported(task):
        # Nos modos Maximo e Agressivo, ajustes com releitura e reversao pelo
        # baseline entram mesmo sem captura transacional propria.
        if (ctx.get("resolved_profile") in policy.EXTENDED and task.id in policy.BASELINE_BACKED
                and task.revert is not None):
            baseline_backed = True
        # Conserto nao tem estado anterior para capturar: o anterior e o defeito.
        # Vale em qualquer perfil, porque aqui ele ja foi escolhido - pelo lote
        # dos modos novos ou pelo botao CONSERTAR, que antes parava neste bloqueio.
        elif task.id in policy.REPAIRS or task.id in policy.ONE_WAY:
            repair = True
        else:
            return {"ok": False, "id": task.id, "name": task.name,
                    "detail": "Aplicação bloqueada: este ajuste ainda não tem captura transacional completa. Use a configuração suportada do Windows ou do fabricante."}
    if baseline_backed:
        # Sem esta releitura, NIC, Nagle e a tela cheia do Fortnite eram gravados
        # de novo a cada login e contados como "reaplicados", mesmo no lugar.
        try:
            current, _ = normalize_result(task.verify(core, ctx))
        except Exception:
            current = False
        if current:
            core.mark_task_applied(task.id, task.name, ctx["resolved_profile"])
            return {"ok": True, "id": task.id, "name": task.name, "already_applied": True,
                    "restart": False, "detail": "Já configurado: estado relido; nenhuma alteração necessária."}
    if task.risk in ('medium','high','experimental') and not ctx.get('_restore_point_checked'):
        from azor_restore_policy import system_restore_once
        protection=system_restore_once(core)
        ctx['_restore_point_checked']=True
        if not protection['ok']:ctx['protection_warning']=protection['detail']
    if progress:
        progress(task.name, "applying", task.description)
    outcome = (_run_repair(core, task, ctx) if repair
               else _run_baseline_backed(core, task, ctx) if baseline_backed
               else transactions.run(core, task, ctx))
    if outcome["ok"]:
        core.mark_task_applied(task.id, task.name, ctx["resolved_profile"])
        if task.restart:
            core.mark_pending_reboot(task.id, task.name)
    core.invalidate_cache()
    return {**outcome, "id": task.id, "name": task.name, "already_applied": False,
            "protection_warning":ctx.get('protection_warning'),
            "restart": bool(outcome["ok"] and task.restart), "risk": task.risk, "can_revert": task.can_revert()}


def apply_task(task_id: str, requested_profile: str = "auto") -> Dict[str, Any]:
    core = _core()
    task = next((t for t in _all_tasks() if t.id == str(task_id)), None)
    if task is None or task.apply is None:
        return {"ok": False, "id": str(task_id), "detail": "Ajuste não disponível."}
    ctx = _context(core, requested_profile)
    try:
        if not task.supports_profile(ctx["resolved_profile"]):
            return {"ok": False, "id": task.id, "skipped": True, "detail": "Preservado pelo perfil escolhido."}
        if task.compatible:
            eligible, detail = task.compatible(core, ctx)
            if not eligible:
                return {"ok": False, "id": task.id, "skipped": True, "detail": detail}
        snap = core.capture_restore_point(force=True)
        reread = core.json.loads(core.STATE_FILE.read_text(encoding="utf-8"))
        if not (snap.get("created_at") and reread.get("created_at") == snap["created_at"] and isinstance(reread.get("registry"), list)):
            raise ValueError("Snapshot não confirmado.")
        return _run_one(core, task, ctx)
    except Exception as exc:
        core.journal("apply_task_failed", id=task.id, error=str(exc))
        return {"ok": False, "id": task.id, "name": task.name, "detail": str(exc)}


def revert_task(task_id: str) -> Dict[str, Any]:
    """Prefer the exact before-image; baseline is only for legacy changes."""
    core = _core()
    task = next((t for t in _all_tasks() if t.id == str(task_id)), None)
    if task is None:
        return {"ok": False, "id": str(task_id), "detail": "Tweak desconhecido."}
    from . import transactions
    pending = [r for r in transactions.history(core) if r.get('task_id') == task.id
               and r.get('status') in ('applied', 'prepared', 'recovery_required')]
    if pending:
        try:
            result = transactions.restore(core, pending[0]['id'])
            core.invalidate_cache()
            return {**result, 'id':task.id, 'name':task.name}
        except Exception as exc:
            return {'ok':False, 'id':task.id, 'detail':str(exc)}
    if task.revert is None:
        return {"ok": False, "id": task.id, "name": task.name, "reversible": False,
                "detail": f"{task.name} não tem reversao individual. " + (task.trade_off or "")}
    try:
        ok, detail = normalize_result(task.revert(core, _context(core, "auto")))
    except Exception as exc:
        core.journal("revert_failed", id=task.id, error=str(exc))
        return {"ok": False, "id": task.id, "name": task.name, "detail": str(exc)}
    try:
        core.invalidate_cache()
    except Exception:
        pass
    if ok:
        # Desfazer e para sempre: sem isto, a reconciliacao da proxima abertura
        # reaplicaria justamente o que o usuario acabou de mandar tirar.
        try:
            core.unmark_task_applied(task.id)
        except Exception:
            pass
    core.journal("revert_task", id=task.id, ok=bool(ok), detail=detail)
    return {"ok": bool(ok), "id": task.id, "name": task.name, "detail": detail}


def revertible_tasks() -> List[Dict[str, Any]]:
    return [{"id": t.id, "name": t.name, "module": t.module, "can_revert": t.can_revert(),
             "reversible": bool(t.reversible), "trade_off": t.trade_off}
            for t in _all_tasks()]


def mode_cleanup_candidates() -> List[Dict[str, Any]]:
    """Itens de teste A/B que a versão anterior dos modos novos aplicou em lote.

    Sairam do Maximo/Agressivo (policy.AB_TEST_ONLY) e o login não os reaplica
    mais, mas continuam no PC até alguém desfazer. Entram aqui so os registrados
    com perfil Maximo/Agressivo e que tem como ser desfeitos. A tela oferece o
    desfazer; nada roda sem o clique do usuário.
    """
    from . import transactions
    core = _core()
    wanted = (core.desired_state() or {}).get("tasks", {}) or {}
    tasks = {t.id: t for t in _all_tasks()}
    out: List[Dict[str, Any]] = []
    for task_id in sorted(policy.AB_TEST_ONLY):
        entry, task = wanted.get(task_id), tasks.get(task_id)
        if not isinstance(entry, dict) or task is None:
            continue
        if str(entry.get("profile") or "") not in policy.EXTENDED:
            continue
        if task.revert is None and not transactions.supported(task):
            continue
        out.append({"id": task_id, "name": task.name, "since": entry.get("first_applied_at")})
    return out


def execute(requested_profile: str = "competitive", progress=None,
            task_ids: Optional[Iterable[str]] = None, preset: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    core = _core()
    if core.os.name != "nt":
        return [{"name": "Compatibility", "status": "failed", "detail": "Windows only", "module": "engine"}]
    ctx = _context(core, requested_profile, preset)
    selected = None if task_ids is None else set(task_ids)
    results = []
    def push(name, status, detail="", module="engine", **metadata):
        row = {"name": name, "status": status, "detail": detail, "module": module, **metadata}
        results.append(row)
        if progress:
            progress(name, status, detail)
    push("Hardware profile", "completed", "Hardware consultado; perfil " + ctx["resolved_profile"] + "."
         + (f" Pré-set: {preset.get('name')}." if preset and preset.get("name") else ""))
    try:
        snap = core.capture_restore_point(force=True)
        reread = core.json.loads(core.STATE_FILE.read_text(encoding="utf-8")) if core.STATE_FILE.exists() else {}
        if not (isinstance(snap, dict) and snap.get("created_at")
                and reread.get("created_at") == snap["created_at"] and isinstance(reread.get("registry"), list)):
            raise ValueError("Snapshot não pôde ser confirmado.")
        push("Backup / Restore", "completed", "Backup local relido. Cada alteração terá também seu próprio estado anterior.")
    except Exception as exc:
        push("Backup / Restore", "failed", str(exc) + " Nenhuma alteração iniciada.")
        return results
    for task in _all_tasks():
        if selected is not None and task.id not in selected:
            continue
        if task.apply is None:
            push(task.name,"not_applicable",task.audit_reason,task.module,id=task.id)
            continue
        if not task.supports_profile(ctx["resolved_profile"]):
            push(task.name, "not_applicable", "Preservado pelo perfil.", task.module, id=task.id)
            continue
        if selected is None:
            eligible, reason = policy.automatic_decision(task, ctx)
            if not eligible:
                push(task.name, "not_applicable", reason, task.module, id=task.id)
                continue
        # Escolhido item a item na tela Tweaks: a escolha é do usuário, não do lote.
        try:
            if task.compatible:
                eligible, reason = task.compatible(core, ctx)
                if not eligible:
                    push(task.name, "not_applicable", reason, task.module, id=task.id)
                    continue
        except Exception as exc:
            push(task.name, "failed", "Compatibilidade não confirmada: " + str(exc), task.module, id=task.id)
            continue
        started = perf_counter()
        try:
            outcome = _run_one(core, task, ctx, progress)
            push(task.name, "completed" if outcome["ok"] else "failed", outcome.get("detail", ""),
                 task.module, **{k:v for k,v in outcome.items() if k not in ("name","ok","detail")},
                 duration_ms=round((perf_counter()-started)*1000,2))
        except Exception as exc:
            push(task.name, "failed", str(exc), task.module, id=task.id,
                 duration_ms=round((perf_counter()-started)*1000,2))
    core.journal("batch_completed", profile=ctx["resolved_profile"], results=results)
    return results
