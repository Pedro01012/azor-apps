"""Relatório para o cliente: uma página HTML com a cara da AZOR.

Junta o que o AZOR já mediu e gravou (nota do diagnóstico, último BOOST, ajustes
ativos, teste de FPS antes/depois e o que ainda depende de BIOS ou peça) numa
página que o técnico entrega ou mostra para o cliente. Não mede nada novo e não
inventa número: o que não foi medido aparece como "não medido".
"""
from __future__ import annotations

import html
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGO = ('<svg viewBox="0 0 64 64" width="44" height="44" aria-hidden="true"><defs><linearGradient id="g" x1="0" x2="1">'
        '<stop offset="0" stop-color="#a8117f"/><stop offset=".55" stop-color="#ff2fc8"/><stop offset="1" stop-color="#ff8be6"/>'
        '</linearGradient></defs><path d="M32 6 58 56H45L32 30 19 56H6Z" fill="url(#g)"/><path d="M24 44h16" stroke="#07070a" '
        'stroke-width="5"/></svg>')

CSS = """
*{box-sizing:border-box}body{margin:0;background:#07070a;color:#f4f1f7;font:15px/1.55 "Segoe UI",system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:36px 28px 60px}
header{display:flex;align-items:center;gap:16px;padding-bottom:22px;border-bottom:1px solid #20202a}
header h1{margin:0;font:800 26px/1.1 Bahnschrift,"Segoe UI",sans-serif;letter-spacing:.06em}
header p{margin:4px 0 0;color:#aca6b7}
h2{margin:34px 0 12px;font:700 13px/1 "Segoe UI",system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#ff66d9}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.card{padding:16px 18px;border:1px solid #20202a;border-radius:14px;background:#101016}
.card small{display:block;color:#7f798b;font:700 11px/1.2 "Segoe UI",system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase}
.card b{display:block;margin-top:8px;font:800 26px/1.1 Bahnschrift,"Segoe UI",sans-serif}
.card span{display:block;margin-top:4px;color:#aca6b7;font-size:13px}
.hero{display:flex;gap:24px;align-items:center;padding:22px;border:1px solid rgba(255,47,200,.35);border-radius:18px;
  background:radial-gradient(500px 200px at 0 0,rgba(255,47,200,.14),transparent 70%),#101016}
.score{font:800 64px/1 Bahnschrift,"Segoe UI",sans-serif;background:linear-gradient(90deg,#fff,#ff8be6);-webkit-background-clip:text;background-clip:text;color:transparent}
.arrow{font:700 22px Bahnschrift;color:#7f798b}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px 8px;border-bottom:1px solid #20202a;text-align:left}
th{color:#7f798b;font-size:12px;letter-spacing:.1em;text-transform:uppercase}
.good{color:#43dc9b}.bad{color:#ff6384}.warn{color:#ffc35c}.muted{color:#aca6b7}
.tag{display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border-radius:999px;font:700 10.5px/1.6 "Segoe UI",system-ui,sans-serif;letter-spacing:.06em;
  border:1px solid rgba(255,47,200,.35);color:#ff9be6;background:rgba(255,47,200,.08)}
ul{margin:0;padding-left:20px}li{margin:6px 0}
footer{margin-top:40px;padding-top:18px;border-top:1px solid #20202a;color:#7f798b;font-size:12.5px}
@media print{body{background:#fff;color:#111}.card,.hero{background:#fff;border-color:#ddd}.muted,.card span{color:#555}}
"""

GOAL_LABELS = {"fps": "Mais FPS", "delay": "Menos delay", "stutter": "Sem travadinhas", "ping": "Internet e ping",
               "leve": "Windows leve", "privacidade": "Privacidade", "visual": "Visual e conforto",
               "reparo": "Consertos", "avancado": "Avançado"}


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _num(v: Any, digits: int = 0) -> str:
    if v is None:
        return "não medido"
    try:
        return f"{float(v):.{digits}f}".replace(".", ",")
    except Exception:
        return _e(v)


def _latest_boost(core) -> Optional[Dict[str, Any]]:
    folder = Path(core.DATA_DIR) / "reports"
    try:
        files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return None
    for path in files[:10]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("tweaks") is not None:
                return data
        except Exception:
            continue
    return None


def _latest_fps(game_diag) -> Optional[Dict[str, Any]]:
    try:
        files = sorted(Path(game_diag.REPORT_DIR).glob("*/Relatorio_AZOR.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return None
    for path in files[:20]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("comparison"):
                return data
        except Exception:
            continue
    return None


def _applied(core) -> Dict[str, List[Dict[str, Any]]]:
    from . import engine, gamer
    names = {t.id: t.name for t in engine._all_tasks()}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for tid in core.desired_task_ids():
        m = gamer.meta(tid)
        groups.setdefault(m["goal"], []).append({"title": m["title"] or names.get(tid, tid), "badges": m["badges"],
                                                 "simple": m["simple"]})
    return groups


def build(core, plan: Dict[str, Any]) -> Dict[str, Any]:
    import azor_game_diag as game_diag
    st = core.load_settings()
    customer = str(st.get("customer_name") or "").strip() or "Cliente"
    hp = plan.get("hardware") or core.hardware_profile()
    first = st.get("first_score") or {}
    boost = _latest_boost(core)
    fps = _latest_fps(game_diag)
    groups = _applied(core)
    total_applied = sum(len(v) for v in groups.values())
    try:
        disp = core.display_refresh_state()
    except Exception:
        disp = {}

    parts: List[str] = []
    parts.append(f"""<header>{LOGO}<div><h1>AZOR · RELATÓRIO DE OTIMIZAÇÃO</h1>
      <p>{_e(customer)} · {_e(time.strftime('%d/%m/%Y %H:%M'))} · {_e((plan.get('pc') or {}).get('label') or 'PC')}</p></div></header>""")

    before = first.get("score")
    parts.append(f"""<h2>Nota do PC</h2><div class="hero">
      {f'<div><div class="muted">Antes</div><div class="score" style="opacity:.55">{_e(before)}</div></div><div class="arrow">→</div>' if before is not None and before != plan.get('score') else ''}
      <div><div class="muted">Agora</div><div class="score">{_e(plan.get('score'))}</div></div>
      <div><b style="font:800 20px Bahnschrift,'Segoe UI',sans-serif">{_e(plan.get('grade'))}</b><div class="muted">{_e(plan.get('done', 0))} itens em dia ·
      {_e(plan.get('todo', 0))} para fazer · {_e(plan.get('manual', 0))} dependem de BIOS/peça</div></div></div>""")

    spec = [("Processador", hp.get("cpu")), ("Placa de vídeo", " + ".join(hp.get("gpus") or []) or None),
            ("Memória", f"{hp.get('ram_gb')} GB" if hp.get("ram_gb") else None),
            ("Monitor", f"{disp.get('current_hz')} Hz" if disp.get("ok") else None)]
    parts.append('<h2>O PC</h2><div class="grid">' + "".join(
        f'<div class="card"><small>{k}</small><span style="color:#f4f1f7;font-size:14.5px;margin-top:8px">{_e(v or "—")}</span></div>'
        for k, v in spec) + "</div>")

    if boost:
        cmp_rows = (boost.get("comparison") or {}).get("metrics") or []
        tw = boost.get("tweaks") or {}
        apps = (boost.get("apps") or {}).get("names") or []
        boot = (boost.get("startup") or {}).get("disabled") or []
        freed = (boost.get("cleanup") or {}).get("freed_mb") or 0
        cards = [("Ajustes aplicados", _e(tw.get("changed", 0)), f"{_e(tw.get('already', 0))} já estavam certos"),
                 ("Apps inúteis removidos", _e(len(apps)), ", ".join(apps[:4]) + ("…" if len(apps) > 4 else "") or "nenhum instalado"),
                 ("Fora da inicialização", _e(len(boot)), ", ".join(map(str, boot[:4])) + ("…" if len(boot) > 4 else "") or "já estava limpa"),
                 ("Espaço liberado", f"{freed / 1024:.1f} GB".replace(".", ",") if freed >= 1024 else f"{freed:.0f} MB", "lixo e temporários")]
        preset_name = (boost.get("preset") or {}).get("name")
        if preset_name:
            parts.append(f'<h2>Pré-set aplicado</h2><div class="card"><b style="font-size:17px">{_e(preset_name)}</b>'
                         f'<span>Configuração escolhida pelo AZOR para este processador, placa de vídeo, memória e disco.</span></div>')
        closed = (boost.get("processes") or {}).get("closed") or []
        if closed:
            cards.append(("Processos inúteis fechados", _e(len(closed)), ", ".join(closed[:4]) + ("…" if len(closed) > 4 else "")))
        parts.append(f'<h2>O que o BOOST fez · {_e(boost.get("mode_label") or "")}</h2><div class="grid">' + "".join(
            f'<div class="card"><small>{t}</small><b>{v}</b><span>{_e(s)}</span></div>' for t, v, s in cards) + "</div>")
        if cmp_rows:
            parts.append('<div class="card" style="margin-top:12px"><table><tr><th>Com o PC parado</th><th>Antes</th><th>Depois</th></tr>' + "".join(
                f"<tr><td>{_e(r['label'])}</td><td>{_num(r['before'])} {_e(r['unit'])}</td><td class=\"{'good' if r['delta'] < 0 else 'muted'}\">"
                f"{_num(r['after'])} {_e(r['unit'])}</td></tr>" for r in cmp_rows) + "</table></div>")

    if fps:
        rows = (fps.get("comparison") or {}).get("rows") or []
        parts.append('<h2>Teste de FPS no jogo (antes × depois)</h2><div class="card"><table><tr><th>Medida</th><th>Antes</th><th>Depois</th><th>Diferença</th></tr>' + "".join(
            f"<tr><td>{_e(r['metric'])}</td><td>{_num(r['before'], 1)}</td><td>{_num(r['after'], 1)}</td>"
            f"<td class=\"{'good' if r.get('improved') else 'bad' if r.get('improved') is False else 'muted'}\">"
            f"{('+' if (r.get('delta') or 0) > 0 else '') + _num(r.get('delta'), 1) if r.get('delta') is not None else '—'}</td></tr>"
            for r in rows) + '</table><p class="muted" style="font-size:12.5px;margin:10px 0 0">Medido com PresentMon, sem overlay e sem mexer no jogo, na mesma partida/mapa antes e depois.</p></div>')

    if groups:
        parts.append(f"<h2>Ajustes ativos neste PC ({total_applied})</h2>")
        for goal in ("fps", "delay", "stutter", "ping", "leve", "privacidade", "visual", "reparo", "avancado"):
            items = groups.get(goal)
            if not items:
                continue
            parts.append(f'<div class="card" style="margin-bottom:10px"><small>{_e(GOAL_LABELS.get(goal, goal))}</small><ul>' + "".join(
                f"<li><b style=\"display:inline;font:600 14px \'Segoe UI\',system-ui,sans-serif\">{_e(i['title'])}</b> "
                + "".join(f'<span class="tag">{_e(b)}</span>' for b in i["badges"])
                + (f'<div class="muted" style="font-size:13px">{_e(i["simple"])}</div>' if i["simple"] else "") + "</li>"
                for i in items) + "</ul></div>")

    manual = [s for s in (plan.get("steps") or []) if s.get("status") in ("todo", "manual")]
    if manual:
        parts.append("<h2>O que ainda dá para melhorar</h2><div class=\"card\"><ul>" + "".join(
            f"<li><b style=\"display:inline;font:600 14px \'Segoe UI\',system-ui,sans-serif\">{_e(s.get('title'))}</b>"
            f"<div class=\"muted\" style=\"font-size:13px\">{_e(s.get('why'))}</div></li>" for s in manual[:12]) + "</ul></div>")

    parts.append("""<footer>Tudo o que o AZOR mudou tem o valor de antes guardado e volta com um clique em
      <b>Reparar &gt; Desfazer tudo</b>. Números marcados como "não medido" não foram inventados: o Windows não os informou.
      <br>AZOR Optimization · otimização gamer</footer>""")

    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>AZOR · {_e(customer)}</title><style>{CSS}</style></head><body><div class=\"wrap\">{''.join(parts)}</div></body></html>")
    folder = Path(core.DATA_DIR) / "reports" / "clientes"
    folder.mkdir(parents=True, exist_ok=True)
    ascii_name = unicodedata.normalize("NFKD", customer).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_")[:40] or "Cliente"
    path = folder / f"AZOR_{slug}_{time.strftime('%Y%m%d_%H%M')}.html"
    path.write_text(doc, encoding="utf-8")
    return {"ok": True, "path": str(path), "detail": f"Relatório salvo: {path.name}"}
