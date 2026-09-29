"""Plano do PC: o que fazer NESTA máquina, em ordem, em português de gente.

Junta cinco leituras que já existiam espalhadas pelos dois apps:
  * perfil de hardware (notebook? quanta RAM? placa de vídeo dedicada?);
  * gargalos estruturais (monitor abaixo da taxa, XMP desligado, canal único);
  * compatibilidade com anti-cheat (Secure Boot, TPM, driver de vídeo);
  * o que o BOOST ainda tem a fazer (tweaks pendentes, apps inúteis,
    programas no boot, lixo no disco);
  * BIOS (XMP e Resizable BAR), que o AZOR não grava mas explica.

Cada passo vira um cartão com um botão. A nota do PC sobe conforme os passos
são feitos - e o cliente enxerga o antes e depois.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

# impacto -> pontos que o passo pendente tira da nota
PENALTY = {3: 14, 2: 7, 1: 3}


def _step(sid, title, why, status, impact, action, badges=(), detail=""):
    return {"id": sid, "title": title, "why": why, "status": status, "impact": impact,
            "action": action, "badges": list(badges), "detail": detail}


def pc_type(hp: Dict[str, Any]) -> Dict[str, Any]:
    """Qual é o tipo deste PC e o que isso muda na prática."""
    ram = float(hp.get("ram_gb") or 0)
    if hp.get("battery"):
        kind, label = "notebook", "Notebook gamer" if hp.get("discrete_gpu") else "Notebook"
    elif not hp.get("discrete_gpu"):
        kind, label = "integrado", "PC com vídeo integrado"
    elif hp.get("tier") == "performance":
        kind, label = "gamer", "PC gamer"
    elif ram and ram < 12:
        kind, label = "entrada", "PC de entrada"
    else:
        kind, label = "intermediario", "PC intermediário"
    tips = {
        "notebook": [
            "Jogue sempre na tomada: na bateria o notebook corta o desempenho pela metade.",
            "Use o BOOST Recomendado. O Extremo esquenta mais e gasta bateria.",
            "Confira em Jogos se cada jogo está usando a placa de vídeo dedicada.",
            "Acima de 90 °C o notebook perde FPS sozinho: limpe as saídas de ar e use um suporte com cooler.",
        ],
        "integrado": [
            "O vídeo integrado usa a RAM do PC como memória de vídeo: dois pentes iguais (dual channel) dão até 40% mais FPS.",
            "Ative o XMP/EXPO na BIOS: memória rápida é FPS direto no vídeo integrado.",
            "Jogue em resolução menor ou com FSR ligado no jogo.",
            "BOOST Recomendado + remover apps inúteis libera RAM, que aqui vira memória de vídeo.",
        ],
        "entrada": [
            "Cada processo a menos conta: rode o BOOST e remova os apps inúteis.",
            "Feche navegador e Discord antes de jogar partidas competitivas.",
            "O upgrade que mais dá FPS por real gasto é ir para 16 GB de RAM em dual channel.",
            "Se o disco for HD mecânico, um SSD acaba com as travadas de carregamento.",
        ],
        "intermediario": [
            "Rode o BOOST Recomendado e deixe o monitor na taxa máxima.",
            "Ative o XMP/EXPO na BIOS: é o ajuste que mais melhora o 1% low.",
            "Mantenha o driver de vídeo atualizado (a cada 2 ou 3 meses).",
        ],
        "gamer": [
            "PC só para jogar? Use o BOOST Extremo e o Modo Turbo em segundo plano.",
            "Na BIOS: XMP/EXPO e Resizable BAR ligados.",
            "Monitor na taxa máxima e driver de vídeo atualizado.",
            "Meça o antes e depois em Jogos > Teste de FPS para ver o ganho real.",
        ],
    }
    return {"kind": kind, "label": label, "tips": tips[kind]}


def build(core, arsenal: Dict[str, Any], compat: Dict[str, Any], bloat: Dict[str, Any],
          startup: Dict[str, Any], cleanup_scan: Dict[str, Any], bios: Dict[str, Any]) -> Dict[str, Any]:
    hp = arsenal.get("hardware_profile") or {}
    steps: List[Dict[str, Any]] = []

    # 1. BOOST: tweaks pendentes do modo recomendado
    tasks = arsenal.get("tasks") or []
    # "in_boost" = o que o BOOST do modo atual pega neste PC, já com o pré-set do hardware.
    chosen = [t for t in tasks if t.get("in_boost", t.get("boost") == "recomendado") and t.get("module") != "repair"]
    pending = [t for t in chosen if t.get("eligible") and t.get("state") != "applied"]
    done = [t for t in chosen if t.get("state") == "applied"]
    repairs = (arsenal.get("repair") or {}).get("found") or []
    steps.append(_step(
        "boost", "Rodar o BOOST",
        "Aplica de uma vez os ajustes que dão FPS e tiram delay, conserta o que outros otimizadores quebraram "
        "e limpa o Windows.",
        "todo" if pending or repairs else "ok", 3, {"kind": "boost"}, ["+FPS", "-DELAY", "+LEVE"],
        (f"{len(pending)} ajuste(s) pendente(s)" + (f" e {len(repairs)} conserto(s)" if repairs else "") + "."
         if pending or repairs else f"{len(done)} ajustes aplicados e confirmados.")))

    # 2. Gargalos estruturais
    try:
        bottleneck = core.bottleneck_report()
    except Exception:
        bottleneck = {}
    display = bottleneck.get("display") or {}
    if display.get("ok"):
        steps.append(_step(
            "monitor", f"Monitor na taxa máxima ({display.get('max_hz')} Hz)",
            "O monitor só mostra tantos quadros quanto a taxa dele. Em 60 Hz, 200 FPS viram 60 na tela.",
            "todo" if display.get("below_max") else "ok", 3, {"kind": "fix", "target": "refresh"},
            ["+FPS", "-DELAY"],
            f"Agora em {display.get('current_hz')} Hz."))
    memory = bottleneck.get("memory") or {}
    if memory.get("ok"):
        steps.append(_step(
            "xmp", "Memória RAM na velocidade certa (XMP/EXPO)",
            "Sem o perfil XMP/EXPO ligado na BIOS, a RAM roda bem abaixo do que você comprou. "
            "É o ajuste de BIOS que mais melhora o 1% low.",
            "todo" if memory.get("xmp_off") else "ok", 3, {"kind": "goto", "target": "hardware", "tab": "bios"},
            ["+FPS", "-STUTTER"],
            (f"Rodando a {memory.get('configured_mhz')} MHz; os pentes aceitam {memory.get('rated_mhz')} MHz."
             if memory.get("xmp_off") else f"Rodando a {memory.get('configured_mhz')} MHz.")))
        if memory.get("single_channel"):
            steps.append(_step(
                "dual_channel", "Dois pentes de RAM (dual channel)",
                "Com um pente só, a memória trabalha com metade da velocidade. Em vídeo integrado isso "
                "chega a 40% menos FPS.", "manual", 2 if hp.get("discrete_gpu") else 3,
                {"kind": "info"}, ["+FPS", "UPGRADE"], "Um pente instalado."))
    for finding in bottleneck.get("findings") or []:
        area = str(finding.get("area") or "")
        title = str(finding.get("title") or "")
        if area == "Disco" or "pré-carregar" in title.lower() or "pre-carregar" in title.lower():
            continue  # aparecem nos passos de limpeza e no BOOST (reparo)
        if area in ("Monitor",) or "XMP" in title or "canal" in title.lower():
            continue
        if finding.get("severity") == "high":
            steps.append(_step("finding_" + area.lower(), title, str(finding.get("detail") or ""), "manual", 2,
                               {"kind": "info"}, [area.upper()], str(finding.get("action") or "")))

    # 3. Compatibilidade com anti-cheat e driver
    for check in compat.get("checks") or []:
        if check["status"] == "ok" or check["id"] in ("refresh", "recording", "game_mode", "disk"):
            continue
        action = ({"kind": "fix", "target": check["id"]} if check.get("can_fix") and not check.get("link")
                  else {"kind": "link", "url": check.get("link")} if check.get("link")
                  else {"kind": "goto", "target": "hardware", "tab": "bios"} if check["id"] in ("secure_boot", "tpm", "vbs")
                  else {"kind": "info"})
        steps.append(_step("compat_" + check["id"], check["name"], f"{check['detail']} Afeta: {check['games']}.",
                           "todo" if check.get("can_fix") else "manual", 3 if check["status"] == "falha" else 2,
                           action, ["ANTI-CHEAT"] if check["id"] in ("secure_boot", "tpm", "vbs", "anticheat") else ["JOGOS"],
                           check.get("fix") or ""))

    # 4. Windows leve
    rec_apps = int(bloat.get("recommended_count") or 0)
    steps.append(_step(
        "bloat", "Remover apps inúteis do Windows",
        "Notícias, Clima, Candy Crush, Copilot e outros vêm instalados e ficam ocupando RAM e disco.",
        "todo" if rec_apps else "ok", 2, {"kind": "goto", "target": "apps", "tab": "remove"}, ["+LEVE", "RAM"],
        f"{rec_apps} app(s) inútil(eis) instalado(s)." if rec_apps else "Nenhum app inútil encontrado."))
    useless = int(startup.get("useless_on") or 0)
    steps.append(_step(
        "startup", "Tirar programas inúteis da inicialização",
        "Cada programa que abre junto com o Windows fica na memória o dia inteiro.",
        "todo" if useless else "ok", 2, {"kind": "goto", "target": "cleanup", "tab": "startup"}, ["+LEVE", "BOOT"],
        f"{useless} programa(s) inútil(eis) abrindo com o Windows." if useless else "Inicialização limpa."))
    junk_mb = float(cleanup_scan.get("boost_mb") or 0)
    disk = cleanup_scan.get("disk") or {}
    steps.append(_step(
        "junk", "Limpar arquivos inúteis",
        "Temporários, cache de atualização e sobras de driver ocupam espaço e deixam o disco mais lento.",
        "todo" if junk_mb >= 300 or float(disk.get("used_pct") or 0) >= 90 else "ok",
        2 if float(disk.get("used_pct") or 0) >= 90 else 1,
        {"kind": "goto", "target": "cleanup"}, ["+ESPAÇO"],
        (f"{junk_mb / 1024:.1f} GB para liberar" if junk_mb >= 1024 else f"{junk_mb:.0f} MB para liberar")
        + (f"; disco em {disk.get('used_pct')}%." if disk.get("used_pct") else ".")))

    # 5. BIOS: Resizable BAR (o XMP já está acima)
    for b in (bios.get("steps") or []):
        if b.get("key") == "resizable_bar" and b.get("status") == "action" and hp.get("discrete_gpu"):
            steps.append(_step("rebar", "Resizable BAR na BIOS",
                               "Deixa o processador enxergar toda a memória da placa de vídeo. Ajuda em vários jogos.",
                               "manual", 1, {"kind": "goto", "target": "hardware", "tab": "bios"}, ["+FPS"],
                               b.get("detail") or ""))

    # Curva, não subtração: cada pendência pesa, mas um PC com muita coisa para
    # fazer não despenca para 0 - a nota tem de subir de forma visível a cada passo.
    penalty = sum(PENALTY.get(int(s["impact"]), 3) for s in steps if s["status"] in ("todo", "manual"))
    score = max(5, min(100, round(100 * math.exp(-penalty / 55))))
    order = {"todo": 0, "manual": 1, "ok": 2}
    steps.sort(key=lambda s: (order[s["status"]], -s["impact"]))
    grade = ("ELITE" if score >= 92 else "ÓTIMO" if score >= 80 else "BOM" if score >= 65
             else "REGULAR" if score >= 45 else "PRECISA DE AJUSTE")
    return {
        "ok": True, "score": score, "grade": grade, "pc": pc_type(hp), "hardware": hp,
        "steps": steps, "todo": sum(1 for s in steps if s["status"] == "todo"),
        "manual": sum(1 for s in steps if s["status"] == "manual"),
        "done": sum(1 for s in steps if s["status"] == "ok"),
    }
