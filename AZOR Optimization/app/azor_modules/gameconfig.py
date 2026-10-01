"""Configuração pronta DENTRO dos jogos: o que o BOOST do Windows não alcança.

O BOOST tira o peso do Windows; o que pesa dentro do jogo (sombra, partícula,
distância de visão, V-Sync) mora no arquivo de configuração de cada jogo. Este
módulo edita esse arquivo com três regras que não se negociam:

  1. SÓ MEXE EM CHAVE QUE JÁ EXISTE. O AZOR não inventa linha: se a versão do
     jogo não tem a chave, ela fica como está e aparece como "não se aplica".
  2. O VALOR TEM QUE TER A MESMA FORMA do que já está lá (verdadeiro/falso,
     inteiro, decimal). Se o jogo mudou o formato, a linha é pulada.
  3. BACKUP ANTES, RELEITURA DEPOIS. A primeira cópia do arquivo do cliente é
     guardada uma vez só e "Voltar o meu" devolve exatamente ela.

O jogo precisa estar FECHADO: ele regrava o arquivo ao sair e desfaria tudo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATE_FILE = "gamecfg_state.json"
LEVELS = ("fps", "equilibrado")

# Cada ajuste: (chave, forma, valor no nível "fps", valor no "equilibrado", o que faz).
# Valor None = não mexe naquele nível. Forma: bool | int | float.
MINECRAFT = (
    ("maxFps", "int", "260", "260", "Sem limite de FPS (260 é o 'ilimitado' do Minecraft)"),
    ("enableVsync", "bool", "false", "false", "V-Sync desligado: menos delay entre o clique e a tela"),
    ("renderDistance", "int", "8", "12", "Distância de visão: o que mais pesa no Minecraft"),
    ("simulationDistance", "int", "5", "8", "Até onde o jogo calcula mobs e plantações"),
    ("entityShadows", "bool", "false", "false", "Sem sombra embaixo de mobs e itens"),
    ("particles", "int", "2", "1", "Partículas no mínimo (2) ou reduzidas (1)"),
    ("graphicsMode", "int", "0", "1", "Gráficos 'Rápido' (0) ou 'Elaborado' (1)"),
    ("fancyGraphics", "bool", "false", "true", "Gráficos rápidos nas versões antigas"),
    ("entityDistanceScaling", "float", "0.75", "1.0", "Mobs e itens somem um pouco mais perto"),
    ("biomeBlendRadius", "int", "0", "2", "Sem mistura de cor entre biomas"),
    ("useVbo", "bool", "true", "true", "Usa a placa de vídeo para os blocos (versões antigas)"),
)

CS2 = (
    ("setting.mat_vsync", "int", "0", "0", "V-Sync desligado: menos delay"),
    ("setting.videocfg_shadow_quality", "int", "0", "1", "Qualidade de sombra"),
    ("setting.videocfg_dynamic_shadows", "int", "0", "1", "Só sombras do sol (sem sombra dinâmica de tudo)"),
    ("setting.videocfg_particle_detail", "int", "0", "1", "Fumaça e efeitos mais leves"),
    ("setting.videocfg_ao_detail", "int", "0", "1", "Oclusão de ambiente (sombreamento de cantos)"),
    ("setting.msaa_samples", "int", "0", None, "Sem MSAA (o suavizador mais pesado)"),
    ("setting.r_csgo_cmaa_enable", "int", "1", None, "CMAA2: suavizador barato no lugar do MSAA"),
)

KV_LINE = re.compile(r'^(?P<pre>\s*"(?P<key>[^"]+)"\s+")(?P<val>[^"]*)(?P<post>".*)$')
COLON_LINE = re.compile(r"^(?P<key>[^:#\s][^:]*):(?P<val>.*)$")
FORMS = {"bool": re.compile(r"^(true|false)$", re.I), "int": re.compile(r"^-?\d+$"),
         "float": re.compile(r"^-?\d+(\.\d+)?$")}


def _steam_userdata(core) -> List[Path]:
    """Pastas de usuário da Steam (userdata/<id>) que existem neste PC."""
    roots: List[Path] = []
    path = core.reg_read("HKCU", r"Software\Valve\Steam", "SteamPath").get("value") if hasattr(core, "reg_read") else None
    if path:
        roots.append(Path(str(path)))
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base:
            roots.append(Path(base) / "Steam")
    seen, out = set(), []
    for root in roots:
        data = root / "userdata"
        key = str(data).lower()
        if key in seen or not data.is_dir():
            continue
        seen.add(key)
        out.extend(sorted(p for p in data.iterdir() if p.is_dir()))
    return out


def _cs2_files(core) -> List[Path]:
    files = []
    for user in _steam_userdata(core):
        candidate = user / "730" / "local" / "cfg" / "cs2_video.txt"
        if candidate.is_file():
            files.append(candidate)
    return files


def _minecraft_files(core) -> List[Path]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    candidate = Path(appdata) / ".minecraft" / "options.txt"
    return [candidate] if candidate.is_file() else []


GAMES: Dict[str, Dict[str, Any]] = {
    "minecraft": {"label": "Minecraft Java", "process": "javaw.exe", "table": MINECRAFT, "style": "colon",
                  "files": _minecraft_files,
                  "tip": "Para ir além, instale o Sodium (Fabric): em geral dobra o FPS sem mudar o visual."},
    "cs2": {"label": "Counter-Strike 2", "process": "cs2.exe", "table": CS2, "style": "kv",
            "files": _cs2_files,
            "tip": "Reflex fica nas opções de vídeo do jogo (Ligado + Boost); o arquivo não guarda isso."},
}


# ---------------------------------------------------------------------------
# Leitura e edição de linha
# ---------------------------------------------------------------------------
def _parse(style: str, line: str) -> Optional[Tuple[str, str]]:
    if style == "kv":
        m = KV_LINE.match(line)
        return (m.group("key"), m.group("val")) if m else None
    m = COLON_LINE.match(line.strip("\r\n"))
    return (m.group("key"), m.group("val")) if m else None


def _rewrite(style: str, line: str, value: str) -> str:
    if style == "kv":
        m = KV_LINE.match(line)
        return m.group("pre") + value + m.group("post")
    key = line.split(":", 1)[0]
    return f"{key}:{value}"


def _wanted(table, level: str):
    idx = 2 if level == "fps" else 3
    return {row[0]: (row[1], row[idx], row[4]) for row in table if row[idx] is not None}


def plan_text(style: str, text: str, table, level: str) -> Dict[str, Any]:
    """Calcula o novo texto SEM gravar nada. Pura: é o que os testes chamam."""
    wanted = _wanted(table, level)
    lines = text.splitlines(keepends=True)
    out, changes, skipped, seen = [], [], [], set()
    for raw in lines:
        body = raw.rstrip("\r\n")
        ending = raw[len(body):]
        parsed = _parse(style, body)
        if not parsed or parsed[0] not in wanted:
            out.append(raw)
            continue
        key, current = parsed
        form, value, why = wanted[key]
        seen.add(key)
        current_clean = current.strip()
        if not FORMS[form].match(current_clean):
            skipped.append({"key": key, "reason": f"formato diferente do esperado ({current_clean or 'vazio'})"})
            out.append(raw)
            continue
        if form == "bool":
            same = current_clean.lower() == value
        else:
            same = float(current_clean) == float(value)
        if same:
            out.append(raw)
            continue
        out.append(_rewrite(style, body, value) + ending)
        changes.append({"key": key, "from": current_clean, "to": value, "why": why})
    missing = [k for k in wanted if k not in seen]
    return {"text": "".join(out), "changes": changes, "skipped": skipped, "missing": missing}


# ---------------------------------------------------------------------------
# Estado e backup
# ---------------------------------------------------------------------------
def _state_path(core) -> Path:
    return Path(core.DATA_DIR) / STATE_FILE


def _load_state(core) -> Dict[str, Any]:
    try:
        return json.loads(_state_path(core).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(core, state: Dict[str, Any]) -> None:
    _state_path(core).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _read(path: Path) -> str:
    """Lê o arquivo do jogo como UTF-8 de verdade; se não for, ninguém mexe (levanta ValueError)."""
    return path.read_bytes().decode("utf-8")


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _backup_dir(core) -> Path:
    path = Path(core.DATA_DIR) / "gamecfg_backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _running(core, process: str) -> bool:
    try:
        return process.lower() in {str(n).lower() for n in core._process_names()}
    except Exception:
        return False


# ---------------------------------------------------------------------------
# API usada pelo servidor
# ---------------------------------------------------------------------------
def scan(core, level: str = "fps") -> Dict[str, Any]:
    """Quais jogos têm arquivo neste PC e quantos ajustes cada um ganharia."""
    level = level if level in LEVELS else "fps"
    state = _load_state(core)
    rows = []
    for game_id, game in GAMES.items():
        try:
            files = game["files"](core)
        except Exception:
            files = []
        if not files:
            continue
        pending, preview = 0, []
        for path in files:
            try:
                plan = plan_text(game["style"], _read(path), game["table"], level)
            except (OSError, ValueError):
                continue
            pending += len(plan["changes"])
            preview += plan["changes"]
        saved = state.get(game_id) or {}
        rows.append({
            "id": game_id, "label": game["label"], "files": [str(p) for p in files],
            "pending": pending, "preview": preview[:12], "tip": game["tip"],
            "applied": bool(saved.get("files")), "applied_at": saved.get("applied_at"),
            "running": _running(core, game["process"]),
        })
    return {"ok": True, "games": rows, "level": level}


def apply(core, game_id: str, level: str = "fps") -> Dict[str, Any]:
    game = GAMES.get(game_id)
    if not game:
        return {"ok": False, "detail": "Jogo desconhecido."}
    level = level if level in LEVELS else "fps"
    if _running(core, game["process"]):
        return {"ok": False, "detail": f"Feche o {game['label']} antes. Ele regrava o arquivo ao sair e desfaria o ajuste."}
    files = game["files"](core)
    if not files:
        return {"ok": False, "detail": f"Não achei a configuração do {game['label']}. Abra o jogo uma vez, entre no menu e feche."}
    state = _load_state(core)
    entry = state.setdefault(game_id, {"files": {}})
    total, details, problems = 0, [], []
    for path in files:
        try:
            plan = plan_text(game["style"], _read(path), game["table"], level)
        except (OSError, ValueError):
            problems.append(f"{path.name}: não deu para ler (formato inesperado)")
            continue
        if not plan["changes"]:
            continue
        key = str(path)
        if key not in entry["files"]:
            # Só a PRIMEIRA cópia vale: é o arquivo original do cliente, não o que já passou pelo AZOR.
            backup = _backup_dir(core) / f"{game_id}-{hashlib.sha1(key.encode()).hexdigest()[:8]}-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix or '.bak'}"
            shutil.copy2(path, backup)
            if _sha(backup) != _sha(path):
                backup.unlink(missing_ok=True)
                problems.append(f"{path.name}: a cópia de segurança não bateu; nada foi alterado")
                continue
            entry["files"][key] = str(backup)
        try:
            _write(path, plan["text"])
        except PermissionError:
            problems.append(f"{path.name}: somente leitura ou sem permissão")
            continue
        again = plan_text(game["style"], _read(path), game["table"], level)
        if again["changes"]:
            problems.append(f"{path.name}: {len(again['changes'])} ajuste(s) não conferiram")
            continue
        total += len(plan["changes"])
        details += plan["changes"]
    if entry["files"]:
        entry["applied_at"] = time.strftime("%Y-%m-%d %H:%M")
        entry["level"] = level
        _save_state(core, state)
    core.journal("gamecfg_apply", game=game_id, level=level, changes=total, problems=problems)
    if problems and not total:
        return {"ok": False, "detail": "; ".join(problems)}
    if not total:
        return {"ok": True, "detail": f"O {game['label']} já estava assim. Nada precisou mudar.", "changes": []}
    note = f" Atenção: {'; '.join(problems)}." if problems else ""
    return {"ok": True, "changes": details,
            "detail": f"{game['label']}: {total} ajuste(s) gravados e conferidos. Seu arquivo original ficou guardado.{note}"}


def restore(core, game_id: str) -> Dict[str, Any]:
    game = GAMES.get(game_id)
    if not game:
        return {"ok": False, "detail": "Jogo desconhecido."}
    if _running(core, game["process"]):
        return {"ok": False, "detail": f"Feche o {game['label']} antes de voltar o arquivo."}
    state = _load_state(core)
    entry = state.get(game_id) or {}
    files = entry.get("files") or {}
    if not files:
        return {"ok": False, "detail": "O AZOR não guardou nenhuma cópia deste jogo; nada a devolver."}
    restored, problems = 0, []
    for original, backup in files.items():
        src, dst = Path(backup), Path(original)
        if not src.is_file():
            problems.append(f"{dst.name}: a cópia sumiu")
            continue
        try:
            shutil.copy2(src, dst)
        except OSError as exc:
            problems.append(f"{dst.name}: {exc}")
            continue
        if _sha(src) == _sha(dst):
            restored += 1
        else:
            problems.append(f"{dst.name}: não conferiu depois de copiar")
    if restored and not problems:
        state.pop(game_id, None)
        _save_state(core, state)
    core.journal("gamecfg_restore", game=game_id, restored=restored, problems=problems)
    if problems:
        return {"ok": False, "detail": "Não deu para devolver tudo: " + "; ".join(problems)}
    return {"ok": True, "detail": f"{game['label']}: o seu arquivo original voltou."}
