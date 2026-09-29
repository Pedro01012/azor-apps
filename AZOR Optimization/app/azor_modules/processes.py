"""Fechar agora o que roda escondido à toa.

O BOOST tira esses programas do boot e dos serviços, mas o que já está aberto
continua ocupando RAM e CPU até o próximo reinício. Esta etapa fecha só
processos de FUNDO que ninguém usa com a janela aberta: widgets, "Vincular ao
Celular", atualizadores e ajudantes. Nada que possa ter trabalho não salvo
(navegador, Teams, Spotify, Discord, Office) entra aqui.

Tudo volta sozinho quando o Windows ou o próprio programa precisar.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

USELESS = {
    "widgets.exe": "Widgets",
    "widgetservice.exe": "Serviço dos Widgets",
    "phoneexperiencehost.exe": "Vincular ao Celular",
    "yourphone.exe": "Vincular ao Celular",
    "yourphoneserver.exe": "Vincular ao Celular",
    "crossdeviceresume.exe": "Retomar do celular",
    "crossdeviceservice.exe": "Dispositivos Móveis",
    "copilot.exe": "Copilot",
    "cortana.exe": "Cortana",
    "onedrive.exe": "OneDrive",
    "skypeapp.exe": "Skype",
    "skypebackgroundhost.exe": "Skype (fundo)",
    "hxtsr.exe": "Email e Calendário (fundo)",
    "microsoft.photos.exe": "Fotos (fundo)",
    "gamebarpresencewriter.exe": "Game Bar (presença)",
    "adobearm.exe": "Atualizador do Adobe",
    "adobecollabsync.exe": "Sincronização do Adobe",
    "ccxprocess.exe": "Adobe Creative Cloud (fundo)",
    "googleupdate.exe": "Atualizador do Google",
    "googlecrashhandler.exe": "Relatório de erros do Google",
    "googlecrashhandler64.exe": "Relatório de erros do Google",
    "jusched.exe": "Atualizador do Java",
    "jucheck.exe": "Atualizador do Java",
    "ituneshelper.exe": "Ajudante do iTunes",
    "microsoftedgeupdate.exe": "Atualizador do Edge",
}


def running(core) -> List[Dict[str, Any]]:
    procs = core._all_process_memory() if os.name == "nt" else {}
    return [{"exe": name, "label": USELESS[name], "memory_mb": row.get("memory_mb") or 0,
             "instances": row.get("instances") or 1}
            for name, row in procs.items() if name in USELESS]


def close_useless(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    found = running(core)
    if not found:
        if progress:
            progress("Processos inúteis", "completed", "Nada rodando à toa.")
        return {"ok": True, "closed": [], "freed_mb": 0}
    closed, freed = [], 0.0
    for row in found:
        try:
            p = core.run_hidden(["taskkill", "/F", "/T", "/IM", row["exe"]], timeout=20)
            ok = p.returncode == 0
        except Exception:
            ok = False
        if ok:
            closed.append(row["label"])
            freed += float(row["memory_mb"] or 0)
    labels = sorted(set(closed))
    detail = (f"{len(labels)} fechado(s), cerca de {freed:.0f} MB de RAM liberados: " + ", ".join(labels) + "."
              if labels else "Nenhum pôde ser fechado.")
    if progress:
        progress("Processos inúteis", "completed" if labels else "failed", detail)
    core.journal("processes_closed", closed=labels, freed_mb=round(freed))
    return {"ok": bool(labels), "closed": labels, "freed_mb": round(freed)}
