"""Small, explicitly selected edition. Importing this module never changes Windows."""
from __future__ import annotations

import json
import os
from functools import wraps
from pathlib import Path

# id, short title, user-visible consequence, enabled by default
OPTIONS = (
    ("game_mode", "Modo de Jogo", "Ativa a preferência do Windows para jogos.", True),
    ("automatic_pagefile", "Memória gerenciada", "Deixa a paginação com o Windows. Pode exigir reinício.", True),
    ("power_plan", "Energia para jogar", "Plano AZOR na tomada. Pode aumentar calor e consumo.", False),
    ("game_dvr", "Sem gravação de fundo", "Desliga a captura de últimos momentos da Game Bar.", False),
    ("mouse_acceleration_off", "Mouse sem aceleração", "Muda também a sensação do ponteiro no desktop.", False),
    ("usb_suspend_off", "USB sempre disponível", "Desliga suspensão de USB na tomada; aumenta consumo.", False),
)
ALLOWED = frozenset(row[0] for row in OPTIONS)
TITLES = {row[0]: row[1] for row in OPTIONS}


def serialized(method):
    """Prevent two essential windows from modifying Windows concurrently."""
    @wraps(method)
    def run(self, *args, **kwargs):
        import msvcrt
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with (self.data_dir / "operation.lock").open("a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Outro AZOR Essencial já está aplicando ou restaurando. Aguarde.") from exc
            try:
                return method(self, *args, **kwargs)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    return run


def read_manifest(path):
    path = Path(path)
    if not path.exists():
        return {"version": 1, "touched": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("touched"), list)
            or any(not isinstance(x, str) or x not in ALLOWED for x in data["touched"])
            or len(set(data["touched"])) != len(data["touched"])):
        raise ValueError("O registro de restauração está inválido. Preserve os arquivos de backup.")
    return data


def write_manifest(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class EssentialService:
    def __init__(self, data_dir, core=None, engine=None):
        self.data_dir = Path(data_dir)
        self.manifest = self.data_dir / "essential_restore.json"
        self._core, self._engine = core, engine

    def _load(self):
        if self._core is None:
            import azor_core
            from azor_modules import engine
            self._core, self._engine = azor_core, engine
        return self._core, self._engine

    def _tasks(self, ids):
        if not ids or any(x not in ALLOWED for x in ids):
            raise ValueError("Selecione pelo menos um dos ajustes essenciais.")
        _, engine = self._load()
        tasks = [t for t in engine._all_tasks() if t.id in set(ids)]
        if len(tasks) != len(set(ids)) or any(
                not t.reversible or not t.can_revert()
                or t.apply is None or t.verify is None for t in tasks):
            raise ValueError("O catálogo essencial não passou na validação de segurança.")
        return tasks

    def analyze(self, ids, progress=lambda *args: None):
        from azor_modules.base import normalize_result
        core, engine = self._load()
        tasks = self._tasks(ids)
        progress("Seu computador", "reading", "Lendo hardware e compatibilidade. Nenhum ajuste é aplicado.")
        ctx = engine._context(core, "competitive")
        rows = []
        for task in tasks:
            progress(TITLES[task.id], "reading", "Consultando a configuração atual…")
            row = {"id": task.id, "name": TITLES[task.id]}
            try:
                ok, detail = normalize_result(task.verify(core, ctx))
                if ok:
                    row.update(status="applied", detail=detail or "Já está configurado.")
                else:
                    eligible, reason = (task.compatible(core, ctx) if task.compatible
                                        else (True, task.description))
                    row.update(status="recommended" if eligible else "preserved", detail=reason)
            except Exception as exc:
                row.update(status="unknown", detail=f"Não foi possível confirmar: {exc}")
            rows.append(row)
            progress(row["name"], row["status"], row["detail"])
        return {"kind": "analyze", "rows": rows, "hardware": ctx.get("hardware", {})}

    def _validate_baseline(self, task_id):
        """Never record success on a snapshot whose undo data is missing."""
        core, _ = self._load()
        data = core.baseline_state()
        if not isinstance(data, dict) or not data.get("created_at") or not isinstance(data.get("registry"), list):
            raise ValueError("Backup original não confirmado. Ajuste bloqueado.")
        if task_id == "power_plan" and not data.get("power_scheme"):
            raise ValueError("O plano de energia original não foi salvo.")
        if task_id == "automatic_pagefile" and not isinstance(data.get("automatic_pagefile"), bool):
            raise ValueError("A configuração anterior de memória não foi salva.")
        if task_id == "usb_suspend_off":
            usb = data.get("usb_selective_suspend")
            if not isinstance(usb, dict) or any(usb.get(k) not in (0, 1) for k in ("ac", "dc")):
                raise ValueError("A configuração anterior de USB não foi salva.")
        if task_id in ("game_mode", "game_dvr", "mouse_acceleration_off"):
            from azor_modules import registry, input_usb
            keys = (input_usb.KEYS if task_id == "mouse_acceleration_off" else registry.KEYS)[task_id]
            for root, path, name in keys:
                if not any(r.get("root") == root and str(r.get("path", "")).casefold() == path.casefold()
                           and r.get("name") == name and isinstance(r.get("exists"), bool)
                           for r in data["registry"]):
                    raise ValueError("Uma configuração original não foi salva. Ajuste bloqueado.")

    @serialized
    def apply(self, ids, progress=lambda *args: None):
        core, engine = self._load()
        tasks = self._tasks(ids)
        if not core.is_admin():
            raise PermissionError("Abra o AZOR como administrador para aplicar os ajustes.")
        manifest = read_manifest(self.manifest)
        # Verify the log is writable BEFORE Windows changes. A partial failure
        # must be undoable as well, so register attempts, not just successes.
        write_manifest(self.manifest, manifest)
        by_name = {t.name: t for t in tasks}

        def report(name, status, detail):
            task = by_name.get(name)
            if status == "applying":
                if task is None:
                    raise ValueError("Uma ação fora da seleção foi bloqueada.")
                self._validate_baseline(task.id)
                if task.id not in manifest["touched"]:
                    manifest["touched"].append(task.id)
                    write_manifest(self.manifest, manifest)
            progress(TITLES[task.id] if task else name, status, detail)

        results = engine.execute("competitive", progress=report, task_ids=[t.id for t in tasks])
        rows = []
        for result in results:
            if result.get("name") == "Azor Guardian":
                continue
            row = dict(result)
            task = by_name.get(row.get("name"))
            if task:
                row["id"], row["name"] = task.id, TITLES[task.id]
                row["restart"] = bool(task.restart and row.get("status") == "completed"
                                      and not row.get("already_applied"))
            rows.append(row)
        return {"kind": "apply", "rows": rows}

    @serialized
    def restore(self, progress=lambda *args: None):
        core, engine = self._load()
        if not core.is_admin():
            raise PermissionError("Abra o AZOR como administrador para restaurar.")
        manifest = read_manifest(self.manifest)
        rows = []
        for task_id in reversed(manifest["touched"][:]):
            progress(TITLES[task_id], "applying", "Restaurando a configuração original…")
            try:
                result = engine.revert_task(task_id)
                row = {"id": task_id, "name": TITLES[task_id],
                       "status": "completed" if result.get("ok") else "failed",
                       "detail": result.get("detail", ""),
                       "restart": task_id == "automatic_pagefile" and bool(result.get("ok"))}
                if result.get("ok"):
                    manifest["touched"].remove(task_id)
                    write_manifest(self.manifest, manifest)
            except Exception as exc:
                row = {"id": task_id, "name": TITLES[task_id], "status": "failed", "detail": str(exc)}
            rows.append(row)
            progress(row["name"], row["status"], row["detail"])
        return {"kind": "restore", "rows": rows}
