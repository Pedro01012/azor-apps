"""Remover os apps que vêm com o Windows e só ocupam espaço, RAM ou tela.

Veio do WinUtil, com três mudanças:
  * cada app diz em uma frase o que faz e se alguém costuma sentir falta;
  * "recommended" separa lixo de verdade (entra no BOOST) do que é gosto
    pessoal (Fotos, Calculadora, Paint ficam só na lista, desmarcados);
  * o que um jogo precisa NUNCA aparece aqui: Xbox Identity Provider (login
    nos jogos), Xbox TCUI, Gaming Services, Game Bar (o Fortnite chama o
    overlay dela), Microsoft Store, instalador de apps (winget) e runtimes.

Remover um app da Store é definitivo para o AZOR, mas não para o usuário:
qualquer um volta pela Microsoft Store. A tela mostra o link de cada um.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

# pacote, nome, o que é / por que tirar, recomendado, id na Store
_BLOAT = [
    ("Microsoft.BingNews", "Notícias", "Feed de notícias que se atualiza em segundo plano.", True, "9WZDNCRFHVFW"),
    ("Microsoft.BingWeather", "Clima", "Previsão do tempo que atualiza sozinha.", True, "9WZDNCRFJ3Q2"),
    ("Microsoft.BingSearch", "Pesquisa Bing", "Integra o Bing ao Windows.", True, "9NZBF4GT040C"),
    ("Microsoft.BingFinance", "Finanças", "Cotações do Bing.", True, ""),
    ("Microsoft.BingSports", "Esportes", "Resultados do Bing.", True, ""),
    ("Microsoft.News", "Microsoft Notícias", "Outro app de notícias.", True, ""),
    ("Microsoft.StartExperiencesApp", "Feed dos Widgets", "Alimenta o painel de notícias da barra.", True, "9PC1H9VN18CM"),
    ("Microsoft.GetHelp", "Obter Ajuda", "Atalho para o suporte da Microsoft.", True, "9PKDZBMV1H3T"),
    ("Microsoft.Getstarted", "Dicas", "Dicas do Windows que ninguém lê.", True, ""),
    ("Microsoft.WindowsFeedbackHub", "Hub de Comentários", "Envia relatórios para a Microsoft.", True, "9NBLGGH4R32N"),
    ("Microsoft.MicrosoftSolitaireCollection", "Paciência (Solitaire)", "Jogo de cartas com anúncios.", True, ""),
    ("Microsoft.MicrosoftOfficeHub", "Microsoft 365 (atalho)", "Só abre o Office na web; não é o Office.", True, "9WZDNCRD29V9"),
    ("Clipchamp.Clipchamp", "Clipchamp", "Editor de vídeo online da Microsoft.", True, "9P1J8S7CCWWT"),
    ("Microsoft.Todos", "Microsoft To Do", "Lista de tarefas.", True, "9NBLGGH5R558"),
    ("Microsoft.PowerAutomateDesktop", "Power Automate", "Automação de escritório.", True, "9NFTCH6J7FHV"),
    ("Microsoft.Windows.DevHome", "Dev Home", "Painel para programadores.", True, "9N8MHTPHNGVV"),
    ("Microsoft.549981C3F5F10", "Cortana", "Assistente descontinuada.", True, ""),
    ("Microsoft.Copilot", "Copilot (app)", "Assistente de IA residente.", True, "9NHT9RB2F4HD"),
    ("Microsoft.People", "Pessoas", "Contatos antigos do Windows.", True, ""),
    ("Microsoft.WindowsMaps", "Mapas", "Mapas offline que atualizam em segundo plano.", True, ""),
    ("Microsoft.ZuneVideo", "Filmes e TV", "Player antigo de filmes.", True, ""),
    ("Microsoft.MixedReality.Portal", "Portal de Realidade Misturada", "Só serve para óculos Windows MR.", True, ""),
    ("Microsoft.Microsoft3DViewer", "Visualizador 3D", "Abre modelos 3D.", True, ""),
    ("Microsoft.Print3D", "Print 3D", "Impressão 3D.", True, ""),
    ("Microsoft.3DBuilder", "3D Builder", "Modelagem 3D.", True, ""),
    ("Microsoft.SkypeApp", "Skype", "Descontinuado pela Microsoft.", True, ""),
    ("Microsoft.Messaging", "Mensagens", "App antigo de SMS.", True, ""),
    ("Microsoft.OneConnect", "Planos Móveis", "Venda de plano de dados.", True, ""),
    ("Microsoft.Wallet", "Carteira", "Pagamentos antigos.", True, ""),
    ("MicrosoftCorporationII.MicrosoftFamily", "Family Safety", "Controle dos pais pela nuvem.", True, ""),
    ("Microsoft.XboxSpeechToTextOverlay", "Legendas de voz do Xbox", "Overlay de acessibilidade do chat.", True, ""),
    ("Microsoft.YourPhone", "Vincular ao Celular", "Fica rodando para espelhar o celular. Desmarque se você usa.", True, "9NMPJ99VJBWV"),
    ("king.com.CandyCrushSaga", "Candy Crush Saga", "Jogo instalado de propaganda.", True, ""),
    ("king.com.CandyCrushSodaSaga", "Candy Crush Soda", "Jogo instalado de propaganda.", True, ""),
    ("king.com.BubbleWitch3Saga", "Bubble Witch 3", "Jogo instalado de propaganda.", True, ""),
    ("BytedancePte.Ltd.TikTok", "TikTok (pré-instalado)", "Instalado por propaganda.", True, ""),
    ("Facebook.Facebook", "Facebook (pré-instalado)", "Instalado por propaganda.", True, ""),
    ("Facebook.InstagramBeta", "Instagram (pré-instalado)", "Instalado por propaganda.", True, ""),
    ("Disney.37853FC22B2CE", "Disney+ (pré-instalado)", "Instalado por propaganda.", True, ""),
    ("AmazonVideo.PrimeVideo", "Prime Video (pré-instalado)", "Instalado por propaganda.", True, ""),
    ("5A894077.McAfeeSecurity", "McAfee (app da loja)", "Propaganda de antivírus pago.", True, ""),
    ("7EE7776C.LinkedInforWindows", "LinkedIn", "Instalado por propaganda.", True, ""),
    # ---- gosto pessoal: aparecem desmarcados ----
    ("MSTeams", "Microsoft Teams", "Chat e reuniões. Remova se não usa para trabalho ou escola.", False, "XP8BT8DW290MPQ"),
    ("Microsoft.OutlookForWindows", "Outlook (novo)", "E-mail e agenda.", False, "9NRX63209R7B"),
    ("microsoft.windowscommunicationsapps", "Email e Calendário (antigo)", "Substituído pelo Outlook novo.", False, ""),
    ("SpotifyAB.SpotifyMusic", "Spotify (loja)", "Música. Remova se não usa.", False, ""),
    ("MicrosoftWindows.CrossDevice", "Dispositivos Móveis", "Base do espelhamento de celular e do ponto de acesso.", False, "9NTXGKQ8P7N0"),
    ("MicrosoftCorporationII.QuickAssist", "Assistência Rápida", "Suporte remoto da Microsoft.", False, "9P7BP5VNWKX5"),
    ("Microsoft.ZuneMusic", "Media Player", "Player de música e vídeo do Windows.", False, "9WZDNCRFJ3PT"),
    ("Microsoft.MicrosoftStickyNotes", "Notas Autoadesivas", "Post-its na tela.", False, "9NBLGGH4QGHW"),
    ("Microsoft.WindowsSoundRecorder", "Gravador de Som", "Grava áudio do microfone.", False, "9WZDNCRFHWKN"),
    ("Microsoft.WindowsAlarms", "Relógio e Alarmes", "Alarmes e cronômetro.", False, "9WZDNCRFJ3PR"),
    ("Microsoft.WindowsCamera", "Câmera", "Webcam.", False, "9WZDNCRFJBBG"),
    ("Microsoft.Windows.Photos", "Fotos", "Visualizador de imagens padrão.", False, "9WZDNCRFJBH4"),
    ("Microsoft.Paint", "Paint", "Desenho simples.", False, "9PCFS5B6T72H"),
    ("Microsoft.ScreenSketch", "Ferramenta de Captura", "Print da tela (Win+Shift+S).", False, "9MZ95KL8MR0L"),
]

CATALOG = [{"package": p, "name": n, "desc": d, "recommended": r,
            "store": (f"ms-windows-store://pdp/?productid={s}" if s else "")} for p, n, d, r, s in _BLOAT]
BY_PACKAGE = {c["package"].lower(): c for c in CATALOG}

# Processos que seguram o pacote aberto e fazem a remoção falhar.
_STOP_FIRST = {
    "microsoft.yourphone": ["PhoneExperienceHost"],
    "microsoft.startexperiencesapp": ["Widgets", "WidgetService"],
    "microsoft.copilot": ["Copilot"],
    "msteams": ["ms-teams"],
}


def installed(core) -> Dict[str, Any]:
    """Quais apps do catálogo estão instalados agora (para qualquer usuário, se admin)."""
    names = ",".join(json.dumps(c["package"]) for c in CATALOG)
    scope = "-AllUsers" if core.is_admin() else ""
    script = (f"$want=@({names}); "
              f"$have=@(Get-AppxPackage {scope} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name); "
              "$want | Where-Object { $have -contains $_ }")
    try:
        data = core.powershell_json(script, timeout=60)
    except Exception as exc:
        return {"ok": False, "items": [], "detail": f"A lista de apps não pôde ser lida: {exc}"}
    if isinstance(data, str):
        data = [data]
    present = {str(x).lower() for x in (data or [])}
    items = [{**c, "installed": c["package"].lower() in present} for c in CATALOG]
    return {"ok": True, "items": items, "installed_count": sum(1 for i in items if i["installed"]),
            "recommended_count": sum(1 for i in items if i["installed"] and i["recommended"])}


def _remove_script(package: str) -> str:
    q = json.dumps(package)
    stop = "; ".join(f"Stop-Process -Name {json.dumps(p)} -Force -ErrorAction SilentlyContinue"
                     for p in _STOP_FIRST.get(package.lower(), []))
    return ((stop + "; " if stop else "") +
            f"Get-AppxPackage -AllUsers -Name {q} -ErrorAction SilentlyContinue | Sort-Object PackageFullName -Unique | "
            "ForEach-Object { try { Remove-AppxPackage -Package $_.PackageFullName -AllUsers -ErrorAction Stop } "
            "catch { Remove-AppxPackage -Package $_.PackageFullName -ErrorAction SilentlyContinue } }; "
            f"Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue | Where-Object DisplayName -eq {q} | "
            "ForEach-Object { Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction SilentlyContinue | Out-Null }; "
            f"@(Get-AppxPackage -AllUsers -Name {q} -ErrorAction SilentlyContinue).Count")


def remove(core, packages: List[str], progress: Optional[Callable] = None) -> Dict[str, Any]:
    if not core.is_admin():
        return {"ok": False, "results": [], "detail": "Remover apps de todos os usuários exige administrador."}
    rows = []
    wanted = [p for p in packages if p.lower() in BY_PACKAGE]
    for i, package in enumerate(wanted, 1):
        item = BY_PACKAGE[package.lower()]
        if progress:
            progress(item["name"], "applying", f"Removendo {i} de {len(wanted)}…")
        try:
            left = int(str(core.powershell(_remove_script(item["package"]), timeout=180)).strip().splitlines()[-1] or 0)
            ok = left == 0
            detail = "Removido e confirmado." if ok else "O Windows manteve o app (em uso ou protegido)."
        except Exception as exc:
            ok, detail = False, str(exc)[:200]
        rows.append({"package": item["package"], "name": item["name"], "ok": ok, "detail": detail,
                     "store": item["store"]})
        if progress:
            progress(item["name"], "completed" if ok else "failed", detail)
    core.journal("appx_removed", packages=[r["package"] for r in rows if r["ok"]])
    done = sum(1 for r in rows if r["ok"])
    return {"ok": done == len(rows), "results": rows, "removed": done,
            "detail": f"{done} de {len(rows)} app(s) removido(s). Qualquer um volta pela Microsoft Store."}


def recommended_installed(core) -> List[str]:
    state = installed(core)
    return [i["package"] for i in state.get("items", []) if i["installed"] and i["recommended"]]
