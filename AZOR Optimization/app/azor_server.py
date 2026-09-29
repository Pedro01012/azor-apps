"""Servidor local do AZOR: a interface (Edge em modo app) conversa só com ele.

Escuta apenas em 127.0.0.1. Toda escrita exige o token da sessão, que só existe
dentro da página que este servidor entregou, e pedidos de outra origem são
recusados - nenhum site aberto no navegador consegue mandar o AZOR fazer nada.

API
  GET  /api/overview            resumo da tela Início (rápido)
  GET  /api/plan                plano do PC (diagnóstico completo)
  GET  /api/tweaks              catálogo de tweaks com estado atual
  GET  /api/apps /api/bloat     programas (winget) e apps inúteis (AppX)
  GET  /api/cleanup /api/startup
  GET  /api/games /api/hardware /api/bios /api/compat /api/history /api/dns
  POST /api/jobs                qualquer operação que mexe no Windows (em segundo plano)
  GET  /api/jobs/<id>           progresso da operação
  POST /api/action              ações rápidas (monitor, GPU por jogo, BIOS, links)
  POST /api/settings
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

import azor_core as core
import azor_game_diag as game_diag
from azor_jobs import JobManager, BusyError
from azor_modules import transactions
from azor_elevation import run_action as run_operation, validate as validate_operation

if os.name == "nt":
    import azor_input_monitor as input_monitor
    import azor_gamepad as gamepad_monitor
else:  # desenvolvimento fora do Windows: os monitores de periférico não existem
    input_monitor = gamepad_monitor = None

ACTION_LOCK = threading.RLock()
core.GAME_PRIORITY.operation_lock = ACTION_LOCK
JOBS = JobManager(core.DATA_DIR / "jobs", ACTION_LOCK)

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = core.DATA_DIR
RUNTIME_FILE = DATA / "server_runtime.json"
STARTUP_LOG = DATA / "server_startup.log"
BUILD_ID_FILE = ROOT / "BUILD_ID.txt"
VERSION = "3.1"


def _build_id():
    try:
        return BUILD_ID_FILE.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return "dev"


def _ui_fingerprint():
    try:
        h = hashlib.sha256()
        for p in sorted(WEB.rglob("*")):
            if p.is_file() and p.suffix in (".html", ".js", ".css"):
                h.update(p.read_bytes())
        return h.hexdigest()[:16]
    except Exception:
        return "unknown"


def startup_log(message):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with STARTUP_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def write_runtime(url, port):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = RUNTIME_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pid": os.getpid(), "port": int(port), "url": str(url),
                                   "started_at": time.time(), "build_id": _build_id()}, indent=2), encoding="utf-8")
        os.replace(tmp, RUNTIME_FILE)
    except Exception as e:
        startup_log(f"Could not write runtime file: {e}")


def read_runtime():
    try:
        data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def probe_url(url, timeout=0.8):
    try:
        req = Request(str(url).rstrip("/") + "/api/runtime", headers={"Cache-Control": "no-cache"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(data.get("ok")), data
    except Exception:
        return False, {}


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# Leituras pesadas com cache curto. Um clique que muda algo limpa o cache.
# ---------------------------------------------------------------------------
def _cached(key, ttl, fn, force=False):
    return core.cached_reading("srv_" + key, ttl, fn, force=force)


def current_mode():
    mode = core.load_settings().get("performance_mode") or "auto"
    return mode if mode in ("auto", "maximo", "agressivo") else "auto"


def preset_payload(force=False, mode=None):
    from azor_modules import presets
    mode = mode or current_mode()

    def build():
        try:
            data = presets.resolve(core, mode, force)
            presets.remember(core, data)
            return data
        except Exception as exc:
            core.log(f"preset resolve failed: {exc}")
            return {"ok": False, "detail": str(exc), "skip": {}, "add": {}, "notes": [], "chips": [],
                    "base": "agressivo" if mode == "auto" else mode, "mode": mode}
    return _cached("preset_" + mode, 120.0, build, force)


def tweaks_payload(force=False):
    from azor_modules import engine, gamer, presets
    def build():
        preset = preset_payload(force)
        data = engine.arsenal("agressivo", preset=presets.engine_view(preset if preset.get("ok") else None),
                              batch_profile=preset.get("base") or "agressivo")
        data["goals"] = gamer.GOALS
        data["mode"] = preset.get("mode")
        data["preset_name"] = preset.get("name")
        return data
    return _cached("tweaks", 45.0, build, force)


def compat_payload(force=False):
    from azor_modules import gamecompat
    return _cached("compat", 90.0, lambda: gamecompat.report(core), force)


def bloat_payload(force=False):
    from azor_modules import debloat
    return _cached("bloat", 120.0, lambda: debloat.installed(core), force)


def startup_payload(force=False):
    from azor_modules import startup
    return _cached("startup", 30.0, lambda: startup.items(core), force)


def cleanup_payload(force=False):
    from azor_modules import cleanup
    return _cached("cleanup", 60.0, lambda: cleanup.scan(core), force)


def plan_payload(force=False):
    from azor_modules import plan
    def build():
        def safe(fn, fallback):
            try:
                return fn()
            except Exception as exc:
                core.log(f"plan section failed: {exc}")
                return fallback
        return plan.build(core,
                          safe(lambda: tweaks_payload(force), {}),
                          safe(lambda: compat_payload(force), {}),
                          safe(lambda: bloat_payload(force), {}),
                          safe(lambda: startup_payload(force), {}),
                          safe(lambda: cleanup_payload(force), {}),
                          safe(core.bios_copilot, {}))

    def build_and_remember():
        result = build()
        # A primeira nota medida neste PC vira o "antes" do relatório do cliente.
        try:
            st = core.load_settings()
            if not st.get("first_score") and result.get("score") is not None:
                st["first_score"] = {"score": result["score"], "grade": result.get("grade"), "time": time.time()}
                core.save_settings(st)
        except Exception:
            pass
        return result
    return _cached("plan", 60.0, build_and_remember, force)


def turbo_status():
    try:
        timer = core.TIMER_SESSION.query()
    except Exception:
        timer = {}
    try:
        memory = core.MEMORY_ENGINE.status()
    except Exception:
        memory = {}
    try:
        priority = core.GAME_PRIORITY.status()
    except Exception:
        priority = {}
    return {"enabled": bool(core.load_settings().get("turbo")),
            "timer": {"active": bool(timer.get("active")), "actual_ms": timer.get("actual_ms")},
            "memory": {"active": bool(memory.get("running")), "cycles": memory.get("cycles")},
            "priority": {"active": bool(priority.get("running")), "raised": priority.get("raised")}}


def set_turbo(enabled: bool):
    """Modo Turbo: timer 0,5 ms, prioridade automática do jogo e motor de memória.

    Vivem dentro deste processo - por isso o AZOR fica na bandeja e inicia com o
    Windows quando o Turbo está ligado.
    """
    results = []
    if enabled:
        for label, fn in (("Timer 0,5 ms", lambda: core.TIMER_SESSION.enable(0.5)),
                          ("Motor de memória", core.MEMORY_ENGINE.start),
                          ("Prioridade do jogo", core.GAME_PRIORITY.start)):
            try:
                ok, detail = fn()
            except Exception as exc:
                ok, detail = False, str(exc)
            results.append({"name": label, "ok": bool(ok), "detail": str(detail)})
    else:
        for label, fn in (("Timer 0,5 ms", core.TIMER_SESSION.disable),
                          ("Motor de memória", core.MEMORY_ENGINE.stop),
                          ("Prioridade do jogo", core.GAME_PRIORITY.stop)):
            try:
                ok, detail = fn()
            except Exception as exc:
                ok, detail = False, str(exc)
            results.append({"name": label, "ok": bool(ok), "detail": str(detail)})
    st = core.load_settings()
    st["turbo"] = bool(enabled)
    core.save_settings(st)
    if enabled and not core.get_start_with_windows():
        core.set_start_with_windows(True)
    return {"ok": all(r["ok"] for r in results) if enabled else True, "results": results, "turbo": turbo_status()}


def overview_payload():
    hp = core.hardware_profile()
    st = core.load_settings()
    try:
        import azor_autostart
        logon = azor_autostart.status(core, query=False)
    except Exception:
        logon = {}
    cached_plan = core._TTL_CACHE.get("srv_plan")
    return {
        "ok": True, "version": VERSION, "build": _build_id(), "admin": core.is_admin(),
        "windows": core.platform.platform(),
        "pc": {k: hp.get(k) for k in ("label", "tier", "cpu", "gpus", "ram_gb", "discrete_gpu", "battery",
                                     "logical_processors", "cores", "topology")},
        "mode": current_mode(),
        "streamer": bool(st.get("streamer")),
        "technician": bool(st.get("technician")),
        "reduce_motion": bool(st.get("reduce_motion")),
        "customer": st.get("customer_name") or "",
        "last_boost": st.get("last_boost"),
        "turbo": turbo_status(),
        "logon": {"enabled": logon.get("enabled"), "stale": logon.get("stale")},
        "plan": ({k: cached_plan[1].get(k) for k in ("score", "grade", "todo", "manual", "done")}
                 if cached_plan else None),
        "job": JOBS.current(),
        "pending_reboot": pending_reboot(),
    }


def pending_reboot():
    """Ajustes aplicados nesta sessão que só valem depois de reiniciar."""
    try:
        pending = core.desired_state().get("pending_reboot") or {}
        now = core.boot_id()
        return [v.get("name") for v in pending.values() if isinstance(v, dict) and v.get("boot") == now]
    except Exception:
        return []


def history_payload():
    reports = []
    folder = DATA / "reports"
    try:
        for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
            try:
                data = transactions.read(path)
            except Exception:
                continue
            reports.append({"id": data.get("id") or path.stem, "time": data.get("time"),
                            "mode": data.get("mode_label") or data.get("profile"),
                            "detail": data.get("detail"), "ok": data.get("ok")})
    except Exception:
        pass
    return {"ok": True, "transactions": transactions.history(core)[:60], "reports": reports,
            "baseline": bool(core.BASELINE_FILE.exists()),
            "applied": core.desired_task_ids(),
            "protection": _cached("protection", 120.0, core.system_protection_status)}


def games_payload(force=False):
    def safe(fn, fallback):
        try:
            return fn()
        except Exception as exc:
            return {**fallback, "error": str(exc)} if isinstance(fallback, dict) else fallback
    return {
        "ok": True,
        "installed": safe(lambda: core.detect_installed_games(force), []),
        "gpu": safe(core.list_game_gpu_preferences, {}),
        "fortnite": safe(core.detect_fortnite, {}),
        "priority": safe(core.GAME_PRIORITY.status, {}),
        "test": safe(game_diag.status, {}),
        "reports": (safe(game_diag.list_reports, {}) or {}).get("reports", []),
        "display": safe(core.display_refresh_state, {}),
        "rates": safe(core.available_refresh_rates, []),
    }


def hardware_payload(force=False):
    def safe(fn, fallback):
        try:
            return fn()
        except Exception as exc:
            core.log(f"hardware section failed: {exc}")
            return fallback
    return {
        "ok": True,
        "profile": safe(lambda: core.hardware_profile(force), {}),
        "bios": safe(core.bios_snapshot, {}),
        "storage": safe(lambda: core.storage_health(force), {}),
        "drivers": safe(lambda: core.driver_inventory(force), {}),
        "thermal": safe(core.thermal_snapshot, {}),
        "memory": safe(lambda: core.memory_channels_state(force), {}),
        "display": safe(core.display_refresh_state, {}),
        "driver_guide": safe(core.driver_guide, {}),
    }


# ---------------------------------------------------------------------------
# Ações rápidas (não passam pela fila de jobs)
# ---------------------------------------------------------------------------
LINK_PREFIXES = ("https://www.nvidia.com/", "https://www.amd.com/", "https://www.intel.com.br/",
                 "https://www.intel.com/", "ms-windows-store://", "ms-settings:", "https://aka.ms/")


def do_action(name: str, p: dict):
    if name == "open_link":
        url = str(p.get("url") or "")
        if not url.startswith(LINK_PREFIXES):
            return {"ok": False, "detail": "Link não permitido."}
        try:
            if os.name == "nt":
                os.startfile(url)
            else:
                webbrowser.open(url)
            return {"ok": True, "detail": "Aberto."}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
    if name == "open_folder":
        which = str(p.get("which") or "")
        target = {"reports": game_diag.REPORT_DIR, "data": DATA, "clients": DATA / "reports" / "clientes"}.get(which)
        if target is not None:
            Path(target).mkdir(parents=True, exist_ok=True)
        if target and os.name == "nt":
            os.startfile(str(target))
            return {"ok": True}
        return {"ok": False, "detail": "Pasta indisponível."}
    if name == "open_report":
        try:
            target = Path(str(p.get("path") or "")).resolve()
            base = Path(game_diag.REPORT_DIR).resolve()
            if base not in target.parents or target.suffix.lower() not in (".html", ".txt") or not target.is_file():
                return {"ok": False, "detail": "Relatório não encontrado."}
            if os.name == "nt":
                os.startfile(str(target))
            return {"ok": True, "detail": "Abrindo o relatório."}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
    if name == "turbo":
        return set_turbo(bool(p.get("enabled")))
    if name == "startup_set":
        request = {"operation": "startup_set", "scope": p.get("scope"), "name": p.get("item"),
                   "enabled": bool(p.get("enabled"))}
        try:
            validate_operation(request)
        except ValueError as exc:
            return {"ok": False, "detail": str(exc)}
        return run_operation(core, request)
    if name == "refresh_max":
        st = core.display_refresh_state()
        ok, detail = core.set_display_refresh_verified(int(p.get("hz") or st.get("max_hz") or 0))
        return {"ok": ok, "detail": detail, "display": core.display_refresh_state()}
    if name == "game_gpu_high":
        ok, detail = core.set_game_high_performance_gpu(str(p.get("exe") or ""))
        return {"ok": ok, "detail": detail}
    if name == "game_gpu_all":
        ok, detail = core.set_all_games_high_performance_gpu()
        return {"ok": ok, "detail": detail}
    if name == "game_gpu_restore":
        ok, detail = core.restore_game_gpu_preference(str(p.get("exe") or ""))
        return {"ok": ok, "detail": detail}
    if name == "pick_game_exe":
        ok, detail, exe = core.pick_game_executable()
        return {"ok": ok, "detail": detail, "exe": exe}
    if name == "fortnite_preset":
        ok, detail = core.apply_fortnite_competitive_preset()
        return {"ok": ok, "detail": detail}
    if name == "fortnite_restore":
        ok, detail = core.restore_latest_fortnite_config()
        return {"ok": ok, "detail": detail}
    if name == "fortnite_res":
        ok, detail = core.set_fortnite_resolution_quality(int(p.get("percent") or 100))
        return {"ok": ok, "detail": detail}
    if name == "game_test_start":
        return game_diag.start(str(p.get("label") or "antes"), str(p.get("customer") or ""), str(p.get("target") or ""))
    if name == "game_test_stop":
        return game_diag.stop()
    if name == "game_test_setup":
        return game_diag.setup_frame_capture()
    if name == "priority":
        ok, detail = (core.GAME_PRIORITY.start() if p.get("enabled") else core.GAME_PRIORITY.stop())
        return {"ok": ok, "detail": detail}
    if name == "bios_check":
        return core.set_bios_checklist(str(p.get("key") or ""), bool(p.get("done")))
    if name == "reboot_to_firmware":
        return run_operation(core, {"operation": "firmware_reboot", "delay": max(5, min(120, int(p.get("delay") or 15)))})
    if name == "abort_reboot":
        return core.abort_reboot()
    if name == "restart_pc":
        if os.name != "nt":
            return {"ok": False, "detail": "Windows only"}
        core.run_hidden(["shutdown", "/r", "/t", str(int(p.get("delay") or 15)), "/c",
                         "O AZOR vai reiniciar o PC para terminar as otimizações."], timeout=10)
        return {"ok": True, "detail": "Reiniciando em alguns segundos. Salve o que estiver aberto."}
    if name == "export_report":
        from azor_modules import report
        out = report.build(core, plan_payload(True))
        if out.get("ok") and os.name == "nt":
            try:
                os.startfile(out["path"])
            except Exception:
                pass
        return out
    if name == "new_customer":
        st = core.load_settings()
        st["customer_name"] = str(p.get("customer") or "")[:60]
        st.pop("first_score", None)
        core.save_settings(st)
        return {"ok": True, "detail": "Novo atendimento: a nota de agora vira o \"antes\" deste cliente."}
    if name == "flush_dns":
        ok, detail = core.flush_dns()
        return {"ok": ok, "detail": "Cache de DNS limpo." if ok else detail}
    if name == "usb_irq":
        return run_operation(core, {"operation": "usb_irq", "enabled": bool(p.get("enabled"))})
    if name == "input_stop" and input_monitor:
        input_monitor.stop()
        gamepad_monitor.stop()
        return {"ok": True}
    if name == "ping":
        host = str(p.get("host") or "1.1.1.1").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,79}", host):
            return {"ok": False, "detail": "Endereço inválido."}
        return core.ping_test(host)
    if name == "open_panel":
        panel = PANELS.get(str(p.get("panel") or ""))
        if not panel:
            return {"ok": False, "detail": "Painel desconhecido."}
        if os.name != "nt":
            return {"ok": False, "detail": "Disponível só no Windows."}
        try:
            # ShellExecute (startfile) pede o UAC sozinho quando o painel exige administrador;
            # CreateProcess falharia com "elevação necessária".
            os.startfile(panel)
            return {"ok": True, "detail": "Abrindo…"}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
    return {"ok": False, "detail": f"Ação desconhecida: {name}"}


# Painéis do Windows que as telas abrem num clique (lista fechada).
PANELS = {
    "devices": "devmgmt.msc",
    "sound": "mmsys.cpl",
    "network": "ncpa.cpl",
    "power": "powercfg.cpl",
    "taskmgr": "taskmgr.exe",
    "graphics": "ms-settings:display-advancedgraphics",
    "gamemode": "ms-settings:gaming-gamemode",
    "update": "ms-settings:windowsupdate",
    "storage": "ms-settings:storagesense",
    "startup": "ms-settings:startupapps",
    "restore": "rstrui.exe",
}

READ_ONLY_ACTIONS = {"open_link", "open_folder", "open_report", "open_panel", "game_test_start", "game_test_stop", "game_test_setup",
                     "input_stop", "ping", "export_report"}

SETTINGS_KEYS = {"streamer": bool, "start_minimized": bool, "technician": bool, "reduce_motion": bool,
                 "performance_mode": str, "customer_name": str}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
SESSION_TOKEN = secrets.token_urlsafe(24)
TOKEN_HEADER = "X-Azor-Token"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def local_origins(port: int) -> set:
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://[::1]:{port}"}


class Handler(SimpleHTTPRequestHandler):
    server_version = "AzorLocal/3"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def handle_one_request(self):
        try:
            return super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            self.close_connection = True
            return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                         "form-action 'none'")
        super().end_headers()

    def _send_json(self, obj, status=200):
        data = json_bytes(obj)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _same_origin(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip().lower()
        if host and host not in LOCAL_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in local_origins(int(self.server.server_address[1])):
            return False
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        return not site or site in ("same-origin", "none")

    def _reject(self, detail: str, status: int = 403):
        core.log(f"Rejected {self.command} {self.path}: {detail}")
        return self._send_json({"ok": False, "error": detail}, status)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n > 0 else {}
        except Exception:
            return {}

    def _send_index(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        html = html.replace("<!--AZOR_TOKEN-->", f'<meta name="azor-token" content="{SESSION_TOKEN}">')
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream_input_live(self):
        """Server-Sent Events do Laboratório de Periféricos. Pausa sozinho com um jogo na frente."""
        self.close_connection = True
        if not input_monitor:
            return self._send_json({"ok": False, "error": "Windows only"}, 404)
        try:
            input_monitor.start()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            deadline = time.time() + 900
            last_send, quiet = 0.0, False
            while time.time() < deadline:
                if core.game_focused().get("focused"):
                    if not quiet:
                        input_monitor.stop()
                        quiet = True
                    self.wfile.write(b"data: " + json_bytes({"paused": True}) + b"\n\n")
                    self.wfile.flush()
                    time.sleep(1.0)
                    continue
                if quiet:
                    input_monitor.start()
                    quiet = False
                if input_monitor.wait_for_change(0.25):
                    gap = time.monotonic() - last_send
                    if gap < 1 / 144:
                        time.sleep(1 / 144 - gap)
                self.wfile.write(b"data: " + json_bytes(input_monitor.snapshot()) + b"\n\n")
                self.wfile.flush()
                last_send = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except Exception as e:
            core.log(f"input live stream ended: {e}")
        return None

    def do_GET(self):
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        force = "force" in query
        if not self._same_origin():
            return self._reject("Requisição de origem externa recusada.")
        try:
            if path in ("/", "/index.html"):
                return self._send_index()
            if path == "/api/runtime":
                return self._send_json({"ok": True, "pid": os.getpid(), "build_id": _build_id(),
                                        "ui_fingerprint": _ui_fingerprint(), "version": VERSION})
            if path == "/api/overview":
                return self._send_json(overview_payload())
            if path == "/api/monitor":
                return self._send_json(core.monitor_snapshot())
            if path == "/api/plan":
                return self._send_json(plan_payload(force))
            if path == "/api/preset":
                mode = (query.get("mode") or [None])[0]
                if mode not in (None, "auto", "maximo", "agressivo"):
                    return self._send_json({"ok": False, "error": "Modo inválido."}, 400)
                return self._send_json(preset_payload(force, mode))
            if path == "/api/tweaks":
                return self._send_json(tweaks_payload(force))
            if path == "/api/compat":
                return self._send_json(compat_payload(force))
            if path == "/api/apps":
                from azor_modules import apps
                return self._send_json(apps.catalog_with_state(core, force))
            if path == "/api/bloat":
                return self._send_json(bloat_payload(force))
            if path == "/api/cleanup":
                return self._send_json(cleanup_payload(force))
            if path == "/api/startup":
                return self._send_json(startup_payload(force))
            if path == "/api/games":
                return self._send_json(games_payload(force))
            if path == "/api/game-test":
                return self._send_json(game_diag.status())
            if path == "/api/hardware":
                return self._send_json(hardware_payload(force))
            if path == "/api/bios":
                return self._send_json(core.bios_copilot())
            if path == "/api/firmware":
                return self._send_json(core.firmware_boot_status())
            if path == "/api/dns":
                from azor_modules import fixes
                return self._send_json(fixes.dns_state(core))
            if path == "/api/history":
                return self._send_json(history_payload())
            if path == "/api/settings":
                settings = core.load_settings()
                try:
                    settings["start_with_windows"] = core.get_start_with_windows()
                except Exception:
                    pass
                return self._send_json(settings)
            if path == "/api/logs":
                return self._send_json({"text": core.read_log(400)})
            if path.startswith("/api/reports/"):
                report_id = path.rsplit("/", 1)[-1]
                if not re.fullmatch(r"[a-f0-9-]{36}", report_id):
                    return self._send_json({"ok": False, "error": "Relatório inválido."}, 400)
                return self._send_json(transactions.read(DATA / "reports" / (report_id + ".json")))
            if path == "/api/jobs/current":
                return self._send_json({"ok": True, "job": JOBS.current()})
            if path.startswith("/api/jobs/"):
                try:
                    return self._send_json({"ok": True, "job": JOBS.get(path.rsplit("/", 1)[-1])})
                except (ValueError, FileNotFoundError):
                    return self._send_json({"ok": False, "error": "Operação não encontrada."}, 404)
            if path == "/api/input-live":
                if not input_monitor:
                    return self._send_json({"ok": False, "unsupported": True})
                input_monitor.start()
                return self._send_json(input_monitor.snapshot())
            if path == "/api/input-live/stream":
                return self._stream_input_live()
            if path == "/api/gamepad-live":
                if not gamepad_monitor:
                    return self._send_json({"ok": False, "unsupported": True, "pads": []})
                return self._send_json(gamepad_monitor.snapshot())
            if path == "/api/devices":
                return self._send_json({"ok": True, "devices": core.detect_devices(),
                                        "caps": core.input_capabilities()})
            if path == "/api/usb-irq":
                return self._send_json({"ok": True, "state": core.usb_interrupt_affinity_state(force=True),
                                        "load": core.interrupt_load_by_cpu(2.0)})
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except Exception as e:
            core.log(f"GET {path} error: {e}\n{traceback.format_exc()}")
            return self._send_json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._same_origin():
            return self._reject("Requisição de origem externa recusada.")
        if self.headers.get(TOKEN_HEADER) != SESSION_TOKEN:
            return self._reject("Token de sessão ausente ou inválido.")
        data = self._body()
        try:
            if path == "/api/jobs":
                request = {k: v for k, v in data.items() if k != "request_key"}
                try:
                    validate_operation(request)
                except ValueError as exc:
                    return self._send_json({"ok": False, "error": f"Pedido inválido ({exc})."}, 400)
                op = request["operation"]

                def run(progress):
                    return run_operation(core, request, progress)

                def done(result):
                    core.invalidate_cache()
                    if op == "boost" and isinstance(result, dict) and result.get("tweaks") is not None:
                        opts = request.get("options") or {}
                        if "turbo" in opts:
                            set_turbo(bool(opts.get("turbo")))
                try:
                    job = JOBS.submit(op, request, str(data.get("request_key") or ""), run, done)
                except BusyError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, 409)
                except ValueError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, 400)
                return self._send_json({"ok": True, "job": job}, 202)
            if path == "/api/action":
                name = str(data.get("name") or "")
                with ACTION_LOCK:
                    result = do_action(name, data)
                if name not in READ_ONLY_ACTIONS:
                    core.invalidate_cache()
                return self._send_json(result)
            if path == "/api/settings":
                settings = core.load_settings()
                for key, typ in SETTINGS_KEYS.items():
                    if key in data:
                        settings[key] = typ(data[key]) if typ is not bool else bool(data[key])
                if settings.get("performance_mode") not in ("auto", "maximo", "agressivo"):
                    settings["performance_mode"] = "auto"
                if "start_with_windows" in data:
                    core.set_start_with_windows(bool(data["start_with_windows"]))
                settings["start_with_windows"] = core.get_start_with_windows()
                core.save_settings(settings)
                core.invalidate_cache()
                return self._send_json({"ok": True, "settings": settings})
            return self._send_json({"ok": False, "error": "endpoint not found"}, 404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except Exception as e:
            core.log(f"POST {path} error: {e}\n{traceback.format_exc()}")
            return self._send_json({"ok": False, "error": str(e)}, 500)


# ---------------------------------------------------------------------------
# Janela e ciclo de vida
# ---------------------------------------------------------------------------
QUIT_EVENT_NAME = "Local\\AzorOptimizationQuit"


def find_edge():
    for p in (shutil.which("msedge"),
              os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
              os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe")):
        if p and os.path.exists(p):
            return p
    return None


def hide_ui_window(tray, timeout: float = 14.0) -> bool:
    try:
        from azor_tray import find_ui_window
        import ctypes
    except Exception:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_ui_window()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
            if tray:
                tray.notify("AZOR", "O AZOR está na bandeja cuidando do desempenho. Clique para abrir.")
            return True
        time.sleep(0.35)
    return False


def _open_quit_event(create: bool):
    if os.name != "nt":
        return None
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        return (k32.CreateEventW(None, True, False, QUIT_EVENT_NAME) if create
                else k32.OpenEventW(0x0002, False, QUIT_EVENT_NAME)) or None
    except Exception:
        return None


def watch_quit_event(server, tray) -> None:
    handle = _open_quit_event(create=True)
    if not handle:
        return
    import ctypes
    ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
    try:
        if tray:
            tray.stop()
    except Exception:
        pass
    threading.Thread(target=server.shutdown, daemon=True).start()


def open_ui(url, minimized=False, tray=None):
    launch_url = f"{url.rstrip('/')}?b={_build_id()}&fp={_ui_fingerprint()}"
    for _ in range(24):
        if probe_url(url, timeout=0.6)[0]:
            break
        time.sleep(0.25)
    else:
        startup_log(f"UI launch aborted: backend did not answer at {url}")
        return False
    edge = find_edge()
    if edge:
        profile = os.path.join(os.environ.get("LOCALAPPDATA", str(ROOT)), "AzorOptimization", "edge_app")
        try:
            subprocess.Popen([edge, f"--app={launch_url}", "--window-size=1440,900",
                              *([] if minimized else ["--start-maximized"]),
                              "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
                              "--disable-extensions", "--disable-features=msEdgeSidebarV2,msEdgeShoppingAssistant"])
            if minimized:
                threading.Thread(target=hide_ui_window, args=(tray,), daemon=True).start()
            return True
        except Exception as e:
            startup_log(f"Edge launch failed: {e}")
    return bool(webbrowser.open(launch_url))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--autostart", action="store_true")
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", int(args.port or 0)), Handler)
    server.daemon_threads = True
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/"
    write_runtime(url, port)
    startup_log(f"AZOR {VERSION} build={_build_id()} at {url} admin={core.is_admin()}")
    if os.environ.get("AZOR_TEST_MODE") != "1":
        threading.Thread(target=core.run_startup_reconcile, name="azor-reconcile", daemon=True).start()
        if core.load_settings().get("turbo"):
            threading.Thread(target=set_turbo, args=(True,), name="azor-turbo", daemon=True).start()
        threading.Thread(target=lambda: _safe(core.hardware_profile), name="azor-warmup", daemon=True).start()
    _safe(core._sweep_stale_tmp)
    _safe(core.sweep_orphan_gpu_feeds)
    tray = None
    if not args.no_browser and os.name == "nt":
        try:
            from azor_tray import AzorTray
            tray = AzorTray(icon_path=WEB / "assets" / "Azor.ico", tooltip="AZOR",
                            on_open=lambda: open_ui(url),
                            on_exit=lambda: threading.Thread(target=server.shutdown, daemon=True).start(),
                            log=core.log)
            tray.start()
        except Exception as exc:
            startup_log(f"Tray unavailable: {exc}")
    threading.Thread(target=watch_quit_event, args=(server, tray), daemon=True).start()
    if not args.no_browser and not args.no_window:
        # "Abrir minimizado" vale só quando quem abriu foi o login do Windows (--autostart);
        # quem clica no ABRIR AZOR.bat quer ver a janela.
        minimized = args.minimized or (args.autostart and bool(core.load_settings().get("start_minimized")))
        threading.Thread(target=open_ui, args=(url, minimized, tray), daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        for stop in (lambda: tray and tray.stop(), core.GAME_PRIORITY.stop, core.TIMER_SESSION.disable,
                     core.MEMORY_ENGINE.stop, core.MONITOR_SAMPLER.stop,
                     lambda: input_monitor and input_monitor.stop(), lambda: gamepad_monitor and gamepad_monitor.stop()):
            _safe(stop)
        server.server_close()
        try:
            if int(read_runtime().get("pid") or -1) == os.getpid():
                RUNTIME_FILE.unlink()
        except Exception:
            pass


def _safe(fn):
    try:
        return fn()
    except Exception as exc:
        core.log(f"{getattr(fn, '__name__', 'task')} failed: {exc}")
        return None


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        startup_log("FATAL: " + traceback.format_exc())
        raise
