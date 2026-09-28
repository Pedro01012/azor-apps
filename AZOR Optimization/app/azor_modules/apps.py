"""Instalar, atualizar e desinstalar programas pelo winget.

Veio do WinUtil. Ficou só o winget (o Chocolatey saiu: dois gerenciadores
para a mesma tarefa confundiam mais do que ajudavam) e o catálogo foi refeito
para quem joga: primeiro o que faz jogo abrir (runtimes), depois lançadores,
comunicação, gravação, diagnóstico, navegadores e utilitários.

O que está instalado é lido do `winget export`, que devolve JSON e não
depende do idioma do Windows - o `winget list` imprime colunas traduzidas.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

CATEGORIES = [
    {"id": "kit", "label": "Kit para jogos rodarem",
     "hint": "Bibliotecas que os jogos pedem. Resolve 'falta MSVCP140.dll', 'd3dx9_43.dll' e jogo que fecha ao abrir."},
    {"id": "launchers", "label": "Lançadores de jogos", "hint": "Lojas e lançadores."},
    {"id": "chat", "label": "Comunicação", "hint": "Voz e chat para jogar em grupo."},
    {"id": "stream", "label": "Gravar e fazer live", "hint": "Gravação de partida, clipes e transmissão."},
    {"id": "tools", "label": "Drivers e diagnóstico", "hint": "Ferramentas de técnico: driver limpo, temperatura, teste de disco."},
    {"id": "browsers", "label": "Navegadores", "hint": "Escolha um navegador."},
    {"id": "utils", "label": "Utilitários", "hint": "Compactadores, busca rápida, acesso remoto e outros."},
]

# id, nome, winget, categoria, descrição curta
_APPS = [
    # ---- kit para jogos ----
    ("vcredist_all", "Visual C++ 2015-2022 (64 bits)", "Microsoft.VCRedist.2015+.x64", "kit",
     "O runtime que quase todo jogo atual exige. Obrigatório."),
    ("vcredist_x86", "Visual C++ 2015-2022 (32 bits)", "Microsoft.VCRedist.2015+.x86", "kit",
     "Mesma biblioteca para jogos e launchers de 32 bits."),
    ("vcredist_2013", "Visual C++ 2013 (64 bits)", "Microsoft.VCRedist.2013.x64", "kit", "Jogos de 2013 a 2016."),
    ("vcredist_2013_x86", "Visual C++ 2013 (32 bits)", "Microsoft.VCRedist.2013.x86", "kit", "Jogos de 2013 a 2016 em 32 bits."),
    ("vcredist_2012", "Visual C++ 2012 (64 bits)", "Microsoft.VCRedist.2012.x64", "kit", "Jogos de 2012 a 2014."),
    ("vcredist_2010", "Visual C++ 2010 (64 bits)", "Microsoft.VCRedist.2010.x64", "kit", "Jogos antigos."),
    ("vcredist_2010_x86", "Visual C++ 2010 (32 bits)", "Microsoft.VCRedist.2010.x86", "kit", "Jogos antigos em 32 bits."),
    ("vcredist_2008", "Visual C++ 2008 (64 bits)", "Microsoft.VCRedist.2008.x64", "kit", "Jogos bem antigos."),
    ("vcredist_2008_x86", "Visual C++ 2008 (32 bits)", "Microsoft.VCRedist.2008.x86", "kit", "Jogos bem antigos em 32 bits."),
    ("directx", "DirectX (runtime completo)", "Microsoft.DirectX", "kit",
     "Arquivos d3dx9, d3dx10, d3dx11 e XAudio que jogos antigos procuram."),
    ("dotnet8", ".NET Desktop Runtime 8", "Microsoft.DotNet.DesktopRuntime.8", "kit", "Launchers, mods e ferramentas feitos em .NET."),
    ("dotnet9", ".NET Desktop Runtime 9", "Microsoft.DotNet.DesktopRuntime.9", "kit", "Versão mais nova do .NET para apps recentes."),
    ("dotnet6", ".NET Desktop Runtime 6", "Microsoft.DotNet.DesktopRuntime.6", "kit", "Apps e mods mais antigos."),
    ("xna", "XNA Framework 4.0", "Microsoft.XNARedist", "kit", "Terraria, Stardew (versões antigas) e jogos indie."),
    # ---- lançadores ----
    ("steam", "Steam", "Valve.Steam", "launchers", "A maior loja de jogos do PC."),
    ("epic", "Epic Games Launcher", "EpicGames.EpicGamesLauncher", "launchers", "Fortnite, Rocket League e jogos grátis toda semana."),
    ("battlenet", "Battle.net", "Blizzard.BattleNet", "launchers", "Call of Duty, Overwatch, Diablo e WoW."),
    ("eaapp", "EA App", "ElectronicArts.EADesktop", "launchers", "EA FC, Battlefield, Apex, The Sims."),
    ("ubisoft", "Ubisoft Connect", "Ubisoft.Connect", "launchers", "Rainbow Six, Assassin's Creed."),
    ("gog", "GOG Galaxy", "GOG.Galaxy", "launchers", "Jogos sem DRM e biblioteca unificada."),
    ("xbox", "Xbox (Game Pass)", "msstore:9MV0B5HZVK9Z", "launchers", "App do Xbox para PC Game Pass."),
    ("roblox", "Roblox", "Roblox.Roblox", "launchers", "Roblox para PC."),
    ("geforcenow", "GeForce NOW", "Nvidia.GeForceNow", "launchers", "Jogar na nuvem da NVIDIA."),
    ("playnite", "Playnite", "Playnite.Playnite", "launchers", "Junta todas as lojas numa biblioteca só."),
    ("prism", "Prism Launcher (Minecraft)", "PrismLauncher.PrismLauncher", "launchers", "Minecraft com mods, leve."),
    ("curseforge", "CurseForge", "Overwolf.CurseForge", "launchers", "Mods de Minecraft, WoW e outros."),
    # ---- comunicação ----
    ("discord", "Discord", "Discord.Discord", "chat", "Voz e chat para jogar em grupo."),
    ("vesktop", "Vesktop", "Vencord.Vesktop", "chat", "Discord mais leve, com melhor compartilhamento de tela."),
    ("teamspeak", "TeamSpeak 3", "TeamSpeakSystems.TeamSpeakClient", "chat", "Voz de baixíssima latência para times."),
    ("whatsapp", "WhatsApp", "msstore:9NKSQGP7F2NH", "chat", "WhatsApp para PC."),
    ("telegram", "Telegram", "Telegram.TelegramDesktop", "chat", "Mensagens e grupos."),
    # ---- gravar / live ----
    ("obs", "OBS Studio", "OBSProject.OBSStudio", "stream", "Gravar e fazer live com o encoder da placa de vídeo."),
    ("sharex", "ShareX", "ShareX.ShareX", "stream", "Print e gravação de tela rápidos."),
    ("vlc", "VLC", "VideoLAN.VLC", "stream", "Abre qualquer vídeo, inclusive as gravações."),
    ("spotify", "Spotify", "Spotify.Spotify", "stream", "Música."),
    # ---- ferramentas ----
    ("nvcleanstall", "NVCleanstall", "TechPowerUp.NVCleanstall", "tools", "Instala o driver NVIDIA só com o necessário, sem telemetria."),
    ("ddu", "Display Driver Uninstaller (DDU)", "Wagnardsoft.DisplayDriverUninstaller", "tools", "Remove driver de vídeo por completo antes de instalar outro."),
    ("hwinfo", "HWiNFO", "REALiX.HWiNFO", "tools", "Temperatura, clock e sensores de tudo."),
    ("cpuz", "CPU-Z", "CPUID.CPU-Z", "tools", "Mostra processador, placa-mãe e RAM (inclui XMP)."),
    ("gpuz", "GPU-Z", "TechPowerUp.GPU-Z", "tools", "Tudo sobre a placa de vídeo."),
    ("hwmonitor", "HWMonitor", "CPUID.HWMonitor", "tools", "Temperaturas de forma simples."),
    ("afterburner", "MSI Afterburner", "Guru3D.Afterburner", "tools", "Overlay de FPS e curva de ventoinha da placa de vídeo."),
    ("crystaldiskinfo", "CrystalDiskInfo", "CrystalDewWorld.CrystalDiskInfo", "tools", "Saúde do SSD e do HD."),
    ("crystaldiskmark", "CrystalDiskMark", "CrystalDewWorld.CrystalDiskMark", "tools", "Teste de velocidade do disco."),
    ("cinebench", "Cinebench R23", "Maxon.CinebenchR23", "tools", "Teste de desempenho e estabilidade do processador."),
    ("processlasso", "Process Lasso", "BitSum.ProcessLasso", "tools", "Controle fino de prioridade e núcleos por programa."),
    ("autoruns", "Autoruns", "Microsoft.Sysinternals.Autoruns", "tools", "Tudo que inicia com o Windows, em detalhe."),
    ("systeminformer", "System Informer", "WinsiderSS.SystemInformer", "tools", "Gerenciador de tarefas avançado."),
    ("sdio", "Snappy Driver Installer Origin", "GlennDelahoy.SnappyDriverInstallerOrigin", "tools", "Drivers de chipset, rede e som offline."),
    ("openrgb", "OpenRGB", "OpenRGB.OpenRGB", "tools", "Controla o RGB de várias marcas sem os programas pesados de fábrica."),
    # ---- navegadores ----
    ("chrome", "Google Chrome", "Google.Chrome", "browsers", "O navegador mais usado."),
    ("firefox", "Firefox", "Mozilla.Firefox", "browsers", "Rápido e com bom bloqueio de rastreio."),
    ("brave", "Brave", "Brave.Brave", "browsers", "Bloqueia anúncios sozinho."),
    ("operagx", "Opera GX", "Opera.OperaGX", "browsers", "Navegador gamer com limite de RAM e CPU."),
    ("vivaldi", "Vivaldi", "Vivaldi.Vivaldi", "browsers", "Muito personalizável."),
    # ---- utilitários ----
    ("7zip", "7-Zip", "7zip.7zip", "utils", "Abre .zip, .rar e .7z."),
    ("winrar", "WinRAR", "RARLab.WinRAR", "utils", "Compactador clássico."),
    ("everything", "Everything", "voidtools.Everything", "utils", "Acha qualquer arquivo em 1 segundo."),
    ("wiztree", "WizTree", "AntibodySoftware.WizTree", "utils", "Mostra o que está ocupando o disco."),
    ("powertoys", "PowerToys", "Microsoft.PowerToys", "utils", "Ferramentas extras da Microsoft."),
    ("notepadpp", "Notepad++", "Notepad++.Notepad++", "utils", "Editar configs de jogos (.ini, .cfg)."),
    ("anydesk", "AnyDesk", "AnyDesk.AnyDesk", "utils", "Acesso remoto para suporte."),
    ("teamviewer", "TeamViewer", "TeamViewer.TeamViewer", "utils", "Acesso remoto para suporte."),
    ("qbittorrent", "qBittorrent", "qBittorrent.qBittorrent", "utils", "Torrent sem propaganda."),
    ("revo", "Revo Uninstaller", "RevoUninstaller.RevoUninstaller", "utils", "Desinstala e limpa as sobras."),
    ("bcu", "Bulk Crap Uninstaller", "Klocman.BulkCrapUninstaller", "utils", "Desinstala vários programas de uma vez."),
    ("eartrumpet", "EarTrumpet", "File-New-Project.EarTrumpet", "utils", "Volume por programa na bandeja."),
    ("warp", "Cloudflare WARP", "Cloudflare.Warp", "utils", "VPN grátis; às vezes melhora rota até o servidor."),
    ("parsec", "Parsec", "Parsec.Parsec", "utils", "Jogar remoto e co-op pela internet."),
    ("rufus", "Rufus", "Rufus.Rufus", "utils", "Criar pendrive de formatação do Windows."),
    ("adobereader", "Adobe Acrobat Reader", "Adobe.Acrobat.Reader.64-bit", "utils", "Abrir PDF."),
]

KIT_ESSENTIAL = ("vcredist_all", "vcredist_x86", "vcredist_2013", "vcredist_2013_x86", "vcredist_2012",
                 "vcredist_2010", "vcredist_2010_x86", "vcredist_2008", "vcredist_2008_x86", "directx",
                 "dotnet8", "xna")

APPS = [{"id": i, "name": n, "winget": w, "category": c, "desc": d} for i, n, w, c, d in _APPS]
BY_ID = {a["id"]: a for a in APPS}

# Códigos do winget que não são falha para quem pediu instalar/atualizar.
ALREADY_INSTALLED = {-1978335135, 0x8A150061}
NO_UPGRADE = {-1978335189, 0x8A15002B}


def winget_exe() -> Optional[str]:
    found = shutil.which("winget")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
        if candidate.exists():
            return str(candidate)
    return None


def catalog() -> Dict[str, Any]:
    return {"categories": CATEGORIES, "apps": APPS, "kit": list(KIT_ESSENTIAL)}


def _source_args(winget_id: str) -> List[str]:
    if winget_id.startswith("msstore:"):
        return ["--id", winget_id.split(":", 1)[1], "--source", "msstore"]
    return ["--id", winget_id, "--exact", "--source", "winget"]


def _common() -> List[str]:
    return ["--accept-source-agreements", "--disable-interactivity"]


def installed_ids(core, force: bool = False) -> Dict[str, Any]:
    """Pacotes instalados que o winget reconhece, por id."""
    def read() -> Dict[str, Any]:
        exe = winget_exe()
        if not exe:
            return {"ok": False, "winget": False, "ids": [],
                    "detail": "O winget não está instalado. Use Reparar > Reinstalar o winget."}
        target = Path(tempfile.gettempdir()) / f"azor-winget-{os.getpid()}-{int(time.time()*1000)}.json"
        try:
            p = core.run_hidden([exe, "export", "-o", str(target), *_common()], timeout=120)
            data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else {}
        except Exception as exc:
            return {"ok": False, "winget": True, "ids": [], "detail": f"O winget não respondeu: {exc}"}
        finally:
            try:
                target.unlink()
            except OSError:
                pass
        ids = set()
        for source in data.get("Sources") or []:
            for pkg in source.get("Packages") or []:
                ident = str(pkg.get("PackageIdentifier") or "")
                if ident:
                    ids.add(ident.lower())
        return {"ok": True, "winget": True, "ids": sorted(ids), "detail": ""}
    return core.cached_reading("winget_installed", 300.0, read, force=force)


def catalog_with_state(core, force: bool = False) -> Dict[str, Any]:
    state = installed_ids(core, force)
    have = set(state.get("ids") or [])
    apps = []
    for app in APPS:
        wid = app["winget"].split(":", 1)[-1].lower()
        apps.append({**app, "installed": wid in have})
    return {**catalog(), "apps": apps, "winget": state.get("winget", False), "detail": state.get("detail", ""),
            "read_ok": state.get("ok", False)}


def _run(core, args: List[str], timeout: int) -> Dict[str, Any]:
    exe = winget_exe()
    if not exe:
        return {"ok": False, "code": None, "detail": "winget não encontrado."}
    try:
        p = core.run_hidden([exe, *args], timeout=timeout)
    except Exception as exc:
        return {"ok": False, "code": None, "detail": str(exc)}
    code = p.returncode
    text = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not set(ln.strip()) <= set("-\\|/ █▒")]
    return {"ok": code == 0, "code": code, "detail": (lines[-1] if lines else "")[:300]}


def install(core, ids: List[str], progress: Optional[Callable] = None) -> Dict[str, Any]:
    rows = []
    for i, app_id in enumerate(ids, 1):
        app = BY_ID.get(app_id)
        if not app:
            rows.append({"id": app_id, "ok": False, "detail": "Programa fora do catálogo."})
            continue
        if progress:
            progress(app["name"], "applying", f"Instalando {i} de {len(ids)}…")
        res = _run(core, ["install", *_source_args(app["winget"]), "--silent",
                          "--accept-package-agreements", *_common()], timeout=1800)
        if res["code"] in ALREADY_INSTALLED:
            res.update(ok=True, detail="Já estava instalado.")
        rows.append({"id": app_id, "name": app["name"], **res})
        if progress:
            progress(app["name"], "completed" if res["ok"] else "failed", res["detail"] or "")
    core.invalidate_cache("winget_installed")
    done = sum(1 for r in rows if r.get("ok"))
    return {"ok": done == len(rows), "results": rows, "detail": f"{done} de {len(rows)} programa(s) instalado(s)."}


def uninstall(core, ids: List[str], progress: Optional[Callable] = None) -> Dict[str, Any]:
    rows = []
    for i, app_id in enumerate(ids, 1):
        app = BY_ID.get(app_id)
        if not app:
            rows.append({"id": app_id, "ok": False, "detail": "Programa fora do catálogo."})
            continue
        if progress:
            progress(app["name"], "applying", f"Desinstalando {i} de {len(ids)}…")
        res = _run(core, ["uninstall", *_source_args(app["winget"]), "--silent", *_common()], timeout=900)
        rows.append({"id": app_id, "name": app["name"], **res})
        if progress:
            progress(app["name"], "completed" if res["ok"] else "failed", res["detail"] or "")
    core.invalidate_cache("winget_installed")
    done = sum(1 for r in rows if r.get("ok"))
    return {"ok": done == len(rows), "results": rows, "detail": f"{done} de {len(rows)} programa(s) desinstalado(s)."}


def upgrade_all(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    if progress:
        progress("Atualizar tudo", "applying", "O winget está baixando as versões novas. Pode levar alguns minutos.")
    res = _run(core, ["upgrade", "--all", "--include-unknown", "--silent", "--accept-package-agreements",
                      *_common()], timeout=3600)
    if res["code"] in NO_UPGRADE:
        res.update(ok=True, detail="Tudo já estava na versão mais nova.")
    core.invalidate_cache("winget_installed")
    if progress:
        progress("Atualizar tudo", "completed" if res["ok"] else "failed", res["detail"])
    return {"ok": res["ok"], "detail": res["detail"] or ("Programas atualizados." if res["ok"] else "Falha ao atualizar."),
            "results": [res]}


def repair_winget(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    if progress:
        progress("winget", "applying", "Baixando o módulo oficial da Microsoft e reinstalando o winget…")
    script = ("[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
              "Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope AllUsers | Out-Null; "
              "Install-Module -Name Microsoft.WinGet.Client -Force -Scope AllUsers -AllowClobber | Out-Null; "
              "Repair-WinGetPackageManager -AllUsers -Force -Latest | Out-Null; 'OK'")
    try:
        core.powershell(script, timeout=900)
    except Exception as exc:
        return {"ok": False, "detail": f"Não foi possível reparar o winget: {exc}"}
    ok = bool(winget_exe())
    core.invalidate_cache("winget_installed")
    return {"ok": ok, "detail": "winget reinstalado e funcionando." if ok else "O winget ainda não foi encontrado."}
