"""Limpeza de disco: mede antes, apaga só o que é lixo e mede de novo.

Junta a Limpeza Rápida do WinUtil com a limpeza segura do Obsidian e soma
o que mais ocupa espaço à toa num PC de jogo: sobras dos instaladores de
driver de vídeo (C:\\NVIDIA, C:\\AMD) e despejos de memória de travamento.

Nunca entram: arquivos pessoais, Downloads, saves, pastas de jogos, pontos de
restauração e o Prefetch (apagar deixa todo programa abrindo do zero).

O cache de shaders fica FORA do BOOST de propósito: apagar faz o jogo
engasgar enquanto recompila. Ele aparece na tela como opção separada, para
usar depois de atualizar o driver de vídeo ou se o jogo tiver bug gráfico.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

FRESH_SECONDS = 3600  # temporário com menos de 1 h pode ser de um instalador rodando agora


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


def targets() -> List[Dict[str, Any]]:
    win = _env("SystemRoot", r"C:\Windows")
    local = _env("LOCALAPPDATA")
    progdata = _env("ProgramData", r"C:\ProgramData")
    drive = _env("SystemDrive", "C:") + "\\"
    temp = _env("TEMP")
    return [
        {"id": "user_temp", "label": "Temporários do usuário", "paths": [temp], "pattern": "*",
         "min_age": FRESH_SECONDS, "boost": True, "admin": False},
        {"id": "windows_temp", "label": "Temporários do Windows", "paths": [os.path.join(win, "Temp")],
         "pattern": "*", "min_age": FRESH_SECONDS, "boost": True, "admin": True},
        {"id": "update_cache", "label": "Downloads antigos do Windows Update",
         "paths": [os.path.join(win, "SoftwareDistribution", "Download")], "pattern": "*",
         "services": ["wuauserv", "bits"], "boost": True, "admin": True},
        {"id": "delivery_cache", "label": "Cache da Otimização de Entrega",
         "paths": [os.path.join(win, r"ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache")],
         "pattern": "*", "services": ["dosvc"], "boost": True, "admin": True},
        {"id": "error_reports", "label": "Relatórios de erro do Windows",
         "paths": [os.path.join(progdata, r"Microsoft\Windows\WER\ReportArchive"),
                   os.path.join(progdata, r"Microsoft\Windows\WER\ReportQueue")], "pattern": "*",
         "boost": True, "admin": True},
        {"id": "crash_dumps", "label": "Despejos de memória de travamentos",
         "paths": [os.path.join(win, "LiveKernelReports"), os.path.join(local, "CrashDumps") if local else ""],
         "pattern": "*.dmp", "files": [os.path.join(win, "MEMORY.DMP")], "recursive_pattern": True,
         "boost": True, "admin": True},
        {"id": "driver_leftovers", "label": "Sobras de instalação de driver de vídeo",
         "paths": [os.path.join(drive, "NVIDIA"), os.path.join(drive, "AMD")], "pattern": "*",
         "boost": True, "admin": True},
        {"id": "fortnite_logs", "label": "Logs e travamentos antigos do Fortnite",
         "paths": [os.path.join(local, r"FortniteGame\Saved\Crashes") if local else ""], "pattern": "*",
         "extra": [(os.path.join(local, r"FortniteGame\Saved\Logs") if local else "", "*-backup-*.log")],
         "boost": True, "admin": False},
        {"id": "thumbnails", "label": "Cache de miniaturas do Explorador",
         "paths": [os.path.join(local, r"Microsoft\Windows\Explorer") if local else ""], "pattern": "thumbcache_*.db",
         "boost": False, "admin": False},
        {"id": "shader_cache", "label": "Cache de shaders (DirectX, NVIDIA, AMD)",
         "paths": [os.path.join(local, "D3DSCache") if local else "",
                   os.path.join(local, r"NVIDIA\DXCache") if local else "",
                   os.path.join(local, r"NVIDIA\GLCache") if local else "",
                   os.path.join(local, r"AMD\DxCache") if local else "",
                   os.path.join(local, r"AMD\DxcCache") if local else "",
                   os.path.join(local, r"AMD\VkCache") if local else ""],
         "pattern": "*", "boost": False, "admin": False,
         "warn": "Os jogos vão engasgar nas primeiras partidas enquanto recompilam. Use só depois de "
                 "atualizar o driver de vídeo ou se aparecer bug gráfico."},
    ]


def _protected() -> set:
    items = [_env("SystemRoot"), _env("USERPROFILE"), _env("ProgramData"), _env("LOCALAPPDATA"), _env("APPDATA"),
             _env("ProgramFiles"), _env("ProgramFiles(x86)")]
    roots = {str(Path(p).resolve()).rstrip("\\/").lower() for p in items if p}
    return roots


def _safe_dir(path: str) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    try:
        if not p.is_dir():
            return None
        full = p.resolve()
    except OSError:
        return None
    text = str(full).rstrip("\\/").lower()
    if len(text) <= 3 or text in _protected():
        return None
    return full


def _size(path: Path) -> int:
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _entries(target: Dict[str, Any]) -> Iterable[Path]:
    now = time.time()
    min_age = int(target.get("min_age") or 0)
    pairs = [(p, target.get("pattern") or "*") for p in target.get("paths") or []] + list(target.get("extra") or [])
    for folder, pattern in pairs:
        root = _safe_dir(folder)
        if root is None:
            continue
        found = root.rglob(pattern) if target.get("recursive_pattern") else root.glob(pattern)
        for entry in found:
            try:
                if entry.is_symlink():
                    continue
                if min_age and now - entry.stat().st_mtime < min_age:
                    continue
            except OSError:
                continue
            yield entry
    for file in target.get("files") or []:
        f = Path(file)
        try:
            if f.is_file():
                yield f
        except OSError:
            continue


def scan(core=None) -> Dict[str, Any]:
    rows = []
    admin = bool(core and core.is_admin())
    for t in targets():
        size = sum(_size(e) for e in _entries(t))
        rows.append({"id": t["id"], "label": t["label"], "bytes": size, "mb": round(size / 1048576, 1),
                     "boost": t["boost"], "admin": t["admin"], "warn": t.get("warn", ""),
                     "blocked": bool(t["admin"] and core is not None and not admin)})
    recycle = recycle_bin_size(core) if core else {"bytes": 0, "items": 0}
    total = sum(r["bytes"] for r in rows if r["boost"])
    return {"ok": True, "targets": rows, "boost_bytes": total, "boost_mb": round(total / 1048576, 1),
            "recycle": recycle, "disk": disk_usage()}


def disk_usage() -> Dict[str, Any]:
    drive = _env("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    try:
        u = shutil.disk_usage(drive)
        return {"drive": drive.rstrip("\\"), "total_gb": round(u.total / 1e9, 1), "free_gb": round(u.free / 1e9, 1),
                "used_pct": round(100 * (u.total - u.free) / u.total, 1)}
    except OSError:
        return {}


def recycle_bin_size(core) -> Dict[str, Any]:
    if os.name != "nt":
        return {"bytes": 0, "items": 0}
    try:
        data = core.powershell_json(
            "$s=(New-Object -ComObject Shell.Application).NameSpace(10); $n=0; $b=0; "
            "foreach($i in $s.Items()){ $n++; $b+= [double]$i.ExtendedProperty('Size') }; "
            "[pscustomobject]@{Items=$n;Bytes=$b}", timeout=40)
        return {"items": int(data.get("Items") or 0), "bytes": int(data.get("Bytes") or 0)}
    except Exception:
        return {"bytes": 0, "items": 0}


def _service(core, verb: str, name: str) -> None:
    try:
        core.run_hidden(["sc", verb, name], timeout=30)
    except Exception:
        pass


def clean(core, ids: List[str], progress: Optional[Callable] = None) -> Dict[str, Any]:
    wanted = [t for t in targets() if t["id"] in set(ids)]
    admin = core.is_admin()
    rows, freed_total = [], 0
    for t in wanted:
        if t["admin"] and not admin:
            rows.append({"id": t["id"], "label": t["label"], "ok": False, "freed": 0,
                         "detail": "Precisa do AZOR como administrador."})
            continue
        if progress:
            progress(t["label"], "applying", "Limpando…")
        entries = list(_entries(t))
        before = sum(_size(e) for e in entries)
        for svc in t.get("services") or []:
            _service(core, "stop", svc)
        for entry in entries:
            try:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink()
            except OSError:
                continue  # em uso: fica para a próxima
        for svc in t.get("services") or []:
            _service(core, "start", svc)
        after = sum(_size(e) for e in _entries(t))
        freed = max(0, before - after)
        freed_total += freed
        rows.append({"id": t["id"], "label": t["label"], "ok": True, "freed": freed,
                     "detail": f"{freed / 1048576:.1f} MB liberados."})
        if progress:
            progress(t["label"], "completed", f"{freed / 1048576:.1f} MB liberados.")
    try:
        core.flush_dns()
    except Exception:
        pass
    core.journal("cleanup", ids=ids, freed=freed_total)
    return {"ok": True, "results": rows, "freed": freed_total, "freed_mb": round(freed_total / 1048576, 1),
            "detail": f"{freed_total / 1048576:.0f} MB liberados.", "disk": disk_usage()}


def boost_ids() -> List[str]:
    return [t["id"] for t in targets() if t["boost"]]


def empty_recycle_bin(core) -> Dict[str, Any]:
    before = recycle_bin_size(core)
    try:
        core.powershell("Clear-RecycleBin -Force -ErrorAction Stop; 'OK'", timeout=120)
    except Exception as exc:
        if "empty" not in str(exc).lower() and "vazia" not in str(exc).lower():
            return {"ok": False, "detail": f"Não foi possível esvaziar: {exc}"}
    after = recycle_bin_size(core)
    freed = max(0, before["bytes"] - after["bytes"])
    return {"ok": after["items"] == 0, "freed": freed, "detail": f"Lixeira esvaziada: {freed / 1048576:.0f} MB."}


def deep_component_cleanup(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    """Remove versões antigas de componentes do Windows (o que a Limpeza de Disco chama de 'Limpeza do Windows Update')."""
    if not core.is_admin():
        return {"ok": False, "detail": "Precisa do AZOR como administrador."}
    before = disk_usage().get("free_gb")
    if progress:
        progress("Componentes antigos do Windows", "applying", "O DISM está limpando. Pode levar de 5 a 20 minutos.")
    try:
        p = core.run_hidden(["dism", "/Online", "/Cleanup-Image", "/StartComponentCleanup"], timeout=3600)
        ok = p.returncode == 0
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
    after = disk_usage().get("free_gb")
    gain = round((after or 0) - (before or 0), 1) if before is not None and after is not None else None
    detail = (f"Limpeza concluída. Espaço livre: {before} GB → {after} GB." if ok
              else "O DISM terminou com erro; tente de novo depois de reiniciar.")
    if progress:
        progress("Componentes antigos do Windows", "completed" if ok else "failed", detail)
    return {"ok": ok, "detail": detail, "gain_gb": gain}
