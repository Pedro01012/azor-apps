from __future__ import annotations

import argparse
import hashlib
import json
import re
import mimetypes
import os
import secrets
import shutil
import socket
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
import azor_input_monitor as input_monitor
import azor_gamepad as gamepad_monitor
import azor_power_guard as power_guard
from azor_jobs import JobManager, BusyError
from azor_modules import transactions
from azor_elevation import run_action as run_operation
from azor_managers import PowerManager, ServiceManager, HardwareDetection

ACTION_LOCK = threading.RLock()
core.GAME_PRIORITY.operation_lock = ACTION_LOCK
JOBS = JobManager(core.DATA_DIR / 'jobs', ACTION_LOCK)

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = core.DATA_DIR
RUNTIME_FILE = DATA / "server_runtime.json"
STARTUP_LOG = DATA / "server_startup.log"
BUILD_ID_FILE = ROOT / "BUILD_ID.txt"


def _build_id():
    try:
        return BUILD_ID_FILE.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return "unknown"


def _ui_fingerprint():
    try:
        h = hashlib.sha256()
        for p in (WEB / "index.html", WEB / "app.js", WEB / "styles.css", WEB / "input-studio.css", WEB / "azor-theme.css", WEB / "performance-center.js"):
            h.update(p.read_bytes())
        return h.hexdigest()[:16]
    except Exception:
        return "unknown"


def startup_log(message):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with STARTUP_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def write_runtime(url, port):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(), "port": int(port), "url": str(url),
            "started_at": time.time(), "build_id": _build_id(),
        }
        tmp = RUNTIME_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
        req = Request(str(url).rstrip("/") + "/api/runtime", headers={"Cache-Control":"no-cache"})
        with urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return False, {}
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(data.get("ok")), data
    except Exception:
        return False, {}


def existing_server_url():
    info = read_runtime()
    url = str(info.get("url") or "")
    if not url:
        return None
    ok, data = probe_url(url)
    if ok and str(data.get("build_id") or "") == _build_id():
        return url
    return None


def wait_runtime(seconds=12.0):
    end = time.time() + max(0.5, float(seconds))
    last = {}
    while time.time() < end:
        info = read_runtime()
        url = str(info.get("url") or "")
        if url:
            ok, data = probe_url(url, timeout=0.7)
            if ok:
                return True, {**info, **data}
            last = info
        time.sleep(0.25)
    return False, last


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")


def _do_action_impl(name: str, payload: dict):
    if name == "open_windows_settings":
        pages = {"animations":"ms-settings:easeofaccess-visualeffects",
                 "notifications":"ms-settings:notifications", "storage":"ms-settings:storagesense"}
        uri = pages.get(str(payload.get("page", "")))
        if not uri:
            return {"ok":False,"detail":"Página de configuração não permitida."}
        try:
            os.startfile(uri)
            return {"ok":True,"applied":False,"detail":"Abertura solicitada ao Windows. Escolha as opções lá; nenhum ajuste foi aplicado pelo AZOR."}
        except Exception:
            return {"ok":False,"detail":"Não foi possível abrir as Configurações do Windows."}
    catalog_actions={
        "game_mode_on":"game_mode","game_dvr_off":"game_dvr","background_apps_off":"background_apps",
        "visual_effects_perf":"visual_effects","power_high":"power_plan","power_max":"power_plan",
        "power_ultimate":"power_plan","power_azor":"power_plan","windows_suggestions_off":"windows_suggestions",
        "transparency_off":"transparency","widgets_off":"widgets",
    }
    if name in catalog_actions:
        return run_operation(core,{"operation":"apply_task","id":catalog_actions[name],"profile":str(payload.get("profile") or "competitive")})
    actions = {
        "game_mode_on": lambda: core.set_game_mode_verified(True),
        "game_dvr_off": lambda: core.set_game_dvr_verified(False),
        "background_apps_off": lambda: core.set_background_apps_verified(True),
        "visual_effects_perf": lambda: core.set_visual_effects_verified(True),
        "power_high": core.set_azor_fps_boost_power,
        "power_max": core.set_azor_fps_boost_power,
        "power_ultimate": core.set_azor_fps_boost_power,
        "power_azor": core.set_azor_fps_boost_power,
        "windows_suggestions_off": core.set_windows_suggestions_off,
        "transparency_off": core.set_transparency_off,
        "widgets_off": core.set_widgets_taskbar_hidden,
        "guardian_repair": lambda: (core.guardian_check_once().get("ok", False), "Guardian verification/repair cycle completed."),
        "agent_startup_on": lambda: (False, "Inicialização automática foi desativada na versão limpa."),
        "flush_dns": core.flush_dns,
        "fortnite_gpu": core.set_fortnite_high_performance_gpu,
        "fortnite_preset": core.apply_fortnite_competitive_preset,
        "fortnite_restore": core.restore_latest_fortnite_config,
        "fortnite_res_70": lambda: core.set_fortnite_resolution_quality(70),
        "fortnite_res_85": lambda: core.set_fortnite_resolution_quality(85),
        "fortnite_res_100": lambda: core.set_fortnite_resolution_quality(100),
        "timer_on": lambda: core.set_latency_target(float(payload.get("period_ms", 0.5))),
        "timer_half": lambda: core.set_latency_target(0.5),
        "timer_one": lambda: core.set_latency_target(1.0),
        "timer_off": core.disable_latency_engine,
        "launch_islc": core.MEMORY_ENGINE.start,
        # "islc_clean_now" foi removida de proposito: purge manual sem pressao de
        # memoria e o padrao "limpador de RAM" que a politica do produto proibe.
        # O motor adaptativo (launch_islc) continua; ele so purga sob pressao.
        "islc_clean_now": lambda: (False, "A limpeza manual foi removida: purgar a standby list sem pressão de memória descarta cache útil e piora o desempenho. O motor adaptativo continua disponível."),
        "islc_stop": core.MEMORY_ENGINE.stop,
        "create_shortcut": core.create_desktop_shortcut,
        "apply_wallpaper": core.apply_azor_wallpaper,
        "restore_wallpaper": core.restore_previous_wallpaper,
        "export_report": core.export_system_report,
        "maintenance_task_on": lambda: (False, "Agendamento automático foi desativado na versão limpa; a manutenção manual continua disponível."),
        "pagefile_auto": lambda: core.set_automatic_pagefile_verified(True),
        "retrim_system": core.retrim_system_drive,
        "storage_refresh": lambda: (True, "Leitura de armazenamento atualizada."),
        "azor_windows_daily": lambda: core.azor_windows_command("Daily"),
        "azor_windows_gameprep": lambda: core.azor_windows_command("GamePrep"),
        "azor_windows_verify": lambda: core.azor_windows_command("Verify"),
        "azor_windows_storage": lambda: core.azor_windows_command("StorageAnalyze"),
        "azor_windows_hardware": lambda: core.azor_windows_command("Hardware"),
        "azor_windows_deep": lambda: core.azor_windows_command("Deep"),
        "azor_windows_drivers": lambda: core.azor_windows_command("Drivers"),
        "azor_windows_restore": lambda: core.azor_windows_command("Restore"),
        # Modulo 3 - camadas de persistencia do plano de energia. Nenhuma delas
        # roda sozinha: cada uma e um clique do usuario, com o custo escrito antes.
        "power_policy_lock_on": lambda: power_guard.set_policy_lock(True),
        "power_policy_lock_off": lambda: power_guard.set_policy_lock(False),
        "fast_startup_off": lambda: power_guard.set_fast_startup(False),
        "fast_startup_on": lambda: power_guard.set_fast_startup(True),
        "power_guard_task_on": lambda: power_guard.set_guard_task(True),
        "power_guard_task_off": lambda: power_guard.set_guard_task(False),
        "power_overlay_max": lambda: power_guard.set_overlay("max"),
        "power_overlay_balanced": lambda: power_guard.set_overlay("balanced"),
        "power_overlay_min": lambda: power_guard.set_overlay("min"),
        "power_watchdog_on": power_guard.WATCHDOG.start,
        "power_watchdog_off": power_guard.WATCHDOG.stop,
    }
    if name == "game_gpu_high":
        ok, detail = core.set_game_high_performance_gpu(str(payload.get("exe") or ""))
        return {"ok": ok, "detail": detail, "games": core.list_game_gpu_preferences().get("games", [])}
    if name == "game_gpu_restore":
        ok, detail = core.restore_game_gpu_preference(str(payload.get("exe") or ""))
        return {"ok": ok, "detail": detail, "games": core.list_game_gpu_preferences().get("games", [])}
    if name == "pick_game_exe":
        ok, detail, exe = core.pick_game_executable()
        return {"ok": ok, "detail": detail, "exe": exe}
    if name == "clean_temp":
        count, size = core.clean_user_temp(int(payload.get("older_hours", 48)))
        return {"ok": True, "detail": f"{count} itens antigos removidos ({size/1024/1024:.1f} MB)."}
    if name == "maintenance_now":
        r = core.daily_maintenance(bool(payload.get("force", False)))
        return {"ok": bool(r.get("ok")), "detail": r.get("detail", ""), "result": r}
    if name == "start_agent":
        return {"ok":False,"detail":"O agente legado de reaplicação foi desativado. Use o Modo de jogo para uma sessão explícita e restaurável."}
    if name == "snapshot":
        try:
            state = core.capture_restore_point(force=True)
            reread = json.loads(core.STATE_FILE.read_text(encoding="utf-8")) if core.STATE_FILE.exists() else {}
            ok = bool(state.get("created_at")) and reread.get("created_at") == state.get("created_at") and isinstance(reread.get("registry"), list)
            return {"ok": ok, "detail": (f"Snapshot criado, relido e verificado em {state.get('created_at')}." if ok else "O snapshot foi solicitado, mas não passou na verificação de releitura.")}
        except Exception as e:
            return {"ok": False, "detail": f"Falha ao criar/verificar snapshot: {e}"}
    if name == "restore_all":
        # "baseline" e o estado anterior ao AZOR; "last" e so o snapshot do ultimo
        # lote. O botao "Restaurar padroes do Windows" precisa do primeiro.
        # Passa pela elevacao como o BOOST: restaurar grava HKLM, plano de energia e
        # paginacao, e a interface roda como usuario comum.
        target = str(payload.get("target") or "baseline")
        if target not in ("baseline", "last"):
            return {"ok": False, "detail": "Destino de restauração inválido."}
        return run_operation(core, {"operation": "restore_all", "target": target})
    if name == "revert_task":
        # Reversao individual: um tweak, um clique, sem desfazer o resto. Pede UAC
        # quando o item mexe fora do registro do usuario.
        task_id = str(payload.get("id") or "")
        if not task_id:
            return {"ok": False, "detail": "Ajuste não informado."}
        try:
            return run_operation(core, {"operation": "revert_task", "id": task_id})
        except ValueError:
            return {"ok": False, "id": task_id, "detail": "Ajuste inválido."}
    if name == "save_controller_remap":
        # Guarda o mapa e devolve `applied: False` - ver o comentario grande em
        # azor_core.controller_remap() sobre por que nada e aplicado hoje.
        payload_map = payload.get("mapping")
        return core.save_controller_remap(payload_map if isinstance(payload_map, dict) else {})
    if name == "prove_task":
        # Mede, aplica e mede de novo. Caro de proposito: e a unica resposta
        # honesta para "este ajuste especifico fez algo no MEU PC?".
        return core.prove_task(str(payload.get("id") or ""), int(payload.get("samples") or 400))
    if name == "reboot_to_firmware":
        # Reinicia o PC direto na configuracao da UEFI. Agendado com folga e
        # cancelavel: um botao que reinicia na hora sequestraria a maquina do cliente.
        return core.reboot_to_firmware(int(payload.get("delay") or 15))
    if name == "abort_reboot":
        return core.abort_reboot()
    if name == "reconcile_now":
        # Reconferencia sob demanda: o mesmo que roda na abertura.
        return {"ok": True, **core.reconcile_desired_state(dry_run=True)}
    if name == "forget_desired":
        core.unmark_task_applied(str(payload.get("id") or ""))
        return {"ok": True, "detail": "O AZOR nao vai mais restaurar este ajuste sozinho."}
    if name == "relaunch_admin":
        return {"ok":False,"detail":"A interface não precisa ser elevada. Execute a ação desejada: a permissão será solicitada somente para ela."}
    if name == "apply_task":
        # Aplicacao individual: o caminho dos itens de risco alto e dos
        # experimentais, que de proposito nao entram no lote de um clique.
        return run_operation(core,{"operation":"apply_task","id":str(payload.get("id") or ""),"profile":str(payload.get("profile") or "auto")})
    if name == "windows_restore_point":
        ok, detail = core.create_windows_restore_point(str(payload.get("description") or "AZOR Optimization"))
        return {"ok": ok, "detail": detail, "protection": core.system_protection_status()}
    if name == "full_optimize":
        # O clique unico passa a valer o nome: catalogo + Input Lab + GPU por jogo
        # + Fortnite, no perfil escolhido no proprio botao BOOST.
        return run_operation(core,{"operation":"full_optimize","profile":str(payload.get("profile") or "competitive")})
    if name == "quick_optimize":
        # Same quick engine and scope; only its required permission is delegated.
        return run_operation(core,{"operation":"quick_optimize","profile":str(payload.get("profile") or "competitive")})
    if name == "power_test_arm":
        return power_guard.persistence_test_arm()
    if name == "power_test_clear":
        return power_guard.persistence_test_clear()
    if name == "stutter_safe_fix":
        return core.apply_stutter_safe_fix()
    if name == "input_monitor_start":
        return input_monitor.start()
    if name == "input_monitor_stop":
        return input_monitor.stop()
    if name == "gamepad_monitor_stop":
        return gamepad_monitor.stop()
    if name == "startup_toggle":
        # One item, one explicit click. There is deliberately no bulk variant.
        ok, detail = core.set_startup_item_enabled(
            str(payload.get("scope") or ""), str(payload.get("name") or ""), bool(payload.get("enabled"))
        )
        return {"ok": ok, "detail": detail, "startup": core.startup_items()}
    if name == "azor_windows_command":
        return core.azor_windows_command(str(payload.get("command") or ""))
    if name == "apply_input_profile":
        kind = str(payload.get("kind") or "")
        profile_index = int(payload.get("profile_index") or 0)
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else None
        return core.apply_input_profile(kind, profile_index, profile)
    fn = actions.get(name)
    if not fn:
        return {"ok": False, "detail": f"Ação desconhecida: {name}"}
    try:
        result = fn()
        if isinstance(result, tuple) and len(result) >= 2:
            first, detail = result[0], result[1]
            # Many setters return None as first item, while tuple actions return bool.
            ok = bool(first) if isinstance(first, bool) else True
            return {"ok": ok, "detail": str(detail)}
        return {"ok": True, "detail": "Ação concluída."}
    except Exception as e:
        core.log(f"Action {name} failed: {e}")
        return {"ok": False, "detail": str(e)}


# Actions that only read or only touch the input listener must not throw away the
# cached system readings - doing so would make the next dashboard poll pay for a
# full re-read after a click that changed nothing on the system.
READ_ONLY_ACTIONS = {
    "input_monitor_start", "input_monitor_stop", "gamepad_monitor_stop", "open_reports_folder", "open_windows_settings",
    "export_report", "logs_clear",
}


def do_action(name: str, payload: dict):
    """Runs the action and then drops cached readings it may have invalidated.

    Without this, a TTL cache would show the user the state from before their own
    click for up to a minute.
    """
    result = _do_action_impl(name, payload)
    if name not in READ_ONLY_ACTIONS:
        try:
            core.invalidate_cache()
        except Exception:
            pass
    return result



# ---------------------------------------------------------------------------
# Local API hardening
#
# The backend listens on 127.0.0.1 and can change power plans, registry values
# and run cleanups. Any page open in the user's browser can send a request to a
# local port - it cannot read the answer, but the side effect already happened.
# Three cheap layers close that:
#   1. the Host header must really be this loopback server (blocks DNS rebinding,
#      where attacker.example resolves to 127.0.0.1);
#   2. a cross-origin Origin / Sec-Fetch-Site is refused;
#   3. every state-changing POST must carry the session token, which only exists
#      inside the page this server itself served.
# ---------------------------------------------------------------------------
SESSION_TOKEN = secrets.token_urlsafe(24)
TOKEN_HEADER = "X-Azor-Token"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def local_origins(port: int) -> set:
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://[::1]:{port}"}



class Handler(SimpleHTTPRequestHandler):
    server_version = "AzorLocal/2D"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        # avoid noisy console; important events go to Azor's own log
        pass

    def handle_one_request(self):
        # A browser closing a stream or a page reload mid-request is normal on
        # localhost. Let those end the connection quietly instead of dumping a
        # traceback that looks like a backend failure.
        try:
            return super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            self.close_connection = True
            return None

    def end_headers(self):
        # The UI changes frequently and runs on localhost. Never let Edge reuse an
        # older app.js/styles.css from a previous AZOR build.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        # Nothing here should ever be sniffed, framed or sent anywhere else.
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
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _stream_input_live(self):
        """Server-Sent Events at ~60 Hz.

        One long-lived connection beats hammering the handler 60 times a second,
        and the browser reconnects on its own if the stream drops. Everything
        stays on 127.0.0.1 and nothing is written to disk.
        """
        # A streaming response must not be followed by a keep-alive read: once the
        # page navigates away the socket is already torn down, and the base
        # handler's next readinto() raises ConnectionAbortedError into the worker.
        self.close_connection = True
        try:
            input_monitor.start()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            # Push on change instead of re-sending an identical frame 60x/s.
            #
            # The fixed 60 Hz loop serialised and wrote a full snapshot even with
            # nobody touching the keyboard, and a real key press still waited for
            # the next tick - up to 16,7 ms of latency added by the transport.
            # Now the loop wakes every 2 ms, sends as soon as the state actually
            # changed (throttled to 60 Hz so a moving mouse cannot flood the
            # socket), and sends a heartbeat every 250 ms to keep the measured
            # polling-rate counters ticking.
            deadline = time.time() + 900  # a stream is a session, not a daemon
            last_send = 0.0
            # 144 Hz: a 60 o desenho atrasava ate um quadro inteiro de monitor de
            # 144/180 Hz. A estimativa de polling, que e a parte cara do snapshot,
            # continua recalculada no maximo 10x/s (POLLING_CACHE_S do monitor).
            MIN_GAP = 1 / 144
            HEARTBEAT = 0.25
            quiet = False
            while time.time() < deadline:
                # ------------------------------------------------------------
                # Modo silencio: com o jogo em primeiro plano, o AZOR sai da
                # frente.
                #
                # O monitor de entrada registra RIDEV_INPUTSINK, que entrega ao
                # AZOR uma copia de TODO relatorio bruto do mouse e do teclado -
                # inclusive sem foco, inclusive dentro da partida. Num mouse de
                # 1000 Hz sao mil mensagens por segundo atravessando um callback
                # Python enquanto o cliente mira. Nada disso serve para nada com
                # a janela escondida: ninguem esta olhando o desenho acender.
                #
                # O watchdog de 8 s nao resolvia porque quem o alimentava era o
                # proprio servidor (`snapshot()` chama `touch()`), nao a pagina.
                # Minimizar para a bandeja mantinha tudo vivo.
                if core.game_focused().get("focused"):
                    if not quiet:
                        input_monitor.stop()
                        quiet = True
                        core.log("Input stream em modo silencio: jogo em primeiro plano.")
                    self.wfile.write(b"data: " + json_bytes(
                        {"paused": True, "reason": "jogo em primeiro plano"}) + b"\n\n")
                    self.wfile.flush()
                    time.sleep(1.0)
                    continue
                if quiet:
                    input_monitor.start()
                    quiet = False
                    core.log("Input stream retomado: o jogo saiu da frente.")

                # Espera o estado MUDAR em vez de perguntar 500 vezes por segundo.
                # O timeout e o proprio heartbeat, entao parado sao 4 despertares
                # por segundo em vez de 500, e uma tecla continua saindo na hora.
                got = input_monitor.wait_for_change(HEARTBEAT)
                if got:
                    gap = time.monotonic() - last_send
                    if gap < MIN_GAP:
                        time.sleep(MIN_GAP - gap)  # teto visual de 144 Hz; amostragem HID continua independente
                snapshot = input_monitor.snapshot()
                last_send = time.monotonic()
                self.wfile.write(b"data: " + json_bytes(snapshot) + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None  # the page navigated away; the watchdog stops the monitor
        except Exception as e:
            core.log(f"input live stream ended: {e}")
        return None

    def _same_origin(self) -> bool:
        """True when the request really came from the page this server serves."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip().lower()
        if host and host not in LOCAL_HOSTS:
            return False
        port = int(self.server.server_address[1])
        origin = self.headers.get("Origin")
        if origin and origin not in local_origins(port):
            return False
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if site and site not in ("same-origin", "none"):
            return False
        return True

    def _reject(self, detail: str, status: int = 403):
        core.log(f"Rejected {self.command} {self.path}: {detail}")
        return self._send_json({"ok": False, "error": detail}, status)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _send_index(self):
        """Serves index.html with this session's token embedded.

        The token has to live in a page only this server can hand out, so a page
        from any other origin cannot read it and cannot forge a POST.
        """
        try:
            html = (WEB / "index.html").read_text(encoding="utf-8")
        except Exception as e:
            return self._send_json({"ok": False, "error": f"index.html: {e}"}, 500)
        meta = f'<meta name="azor-token" content="{SESSION_TOKEN}">'
        if "<!--AZOR_TOKEN-->" in html:
            html = html.replace("<!--AZOR_TOKEN-->", meta)
        else:
            html = html.replace("</head>", f"  {meta}\n</head>", 1)
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return None

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._same_origin():
            return self._reject("Requisicao de origem externa recusada.")
        try:
            if path in ("/", "/index.html"):
                return self._send_index()
            if path.startswith('/api/operations/'):
                try:
                    return self._send_json({'ok':True,'job':JOBS.get(path.rsplit('/',1)[-1])})
                except (ValueError, FileNotFoundError):
                    return self._send_json({'ok':False,'error':'Operação não encontrada.'},404)
            if path == '/api/transactions':
                return self._send_json({'ok':True,'items':transactions.history(core)})
            if path == '/api/pc-overview':
                return self._send_json({'ok':True,**HardwareDetection(core).read()})
            if path == '/api/power-control':
                manager=PowerManager(core)
                plans=manager.plans()
                try:plans['cpu']=manager.cpu_state()
                except Exception as exc:plans['cpu']={'ok':False,'detail':str(exc)}
                return self._send_json(plans)
            if path == '/api/game-mode':
                return self._send_json({'ok':True,**core.GAME_PRIORITY.status(),'power_plans':core.list_power_schemes()})
            if path == '/api/service-control':
                rows=[];manager=ServiceManager(core)
                for name in sorted(manager.OPTIONAL):
                    try:rows.append(manager.state(name))
                    except Exception as exc:rows.append({'name':name,'exists':None,'detail':str(exc)})
                return self._send_json({'ok':True,'items':rows,'note':'Nenhum serviço será desativado automaticamente.'})
            if path.startswith('/api/reports/'):
                report_id=path.rsplit('/',1)[-1]
                if not re.fullmatch(r'[a-f0-9-]{36}',report_id):
                    return self._send_json({'ok':False,'error':'Relatório inválido.'},400)
                try:
                    return self._send_json(transactions.read(core.DATA_DIR/'reports'/(report_id+'.json')))
                except FileNotFoundError:
                    return self._send_json({'ok':False,'error':'Relatório não encontrado.'},404)
            if path == "/api/runtime":
                return self._send_json({
                    "ok": True,
                    "pid": os.getpid(),
                    "port": int(self.server.server_address[1]),
                    "url": f"http://127.0.0.1:{int(self.server.server_address[1])}/",
                    "build_id": _build_id(),
                    "ui_mode": "2d",
                    "ui_fingerprint": _ui_fingerprint(),
                    "server": self.server_version,
                })
            if path == "/api/summary":
                summary = core.system_summary()
                summary["islc"] = core.detect_external_islc_process()
                summary["timer_active"] = bool(core.TIMER_SESSION.active)
                summary["settings"] = core.load_settings()
                return self._send_json(summary)
            if path == "/api/devices":
                devices = core.detect_devices()
                return self._send_json({"ok": True, "devices": devices, "device_count": sum(len(v) for v in devices.values()), "detection": core.device_detection_meta()})
            if path == "/api/input-lab":
                return self._send_json(core.input_lab_snapshot())
            if path == "/api/monitor":
                return self._send_json(core.monitor_snapshot())
            if path == "/api/logs":
                return self._send_json({"text": core.read_log(450)})
            if path == "/api/network":
                return self._send_json(core.network_snapshot())
            if path == "/api/fortnite":
                return self._send_json(core.detect_fortnite())
            if path == "/api/games-gpu":
                return self._send_json(core.list_game_gpu_preferences())
            if path == "/api/settings":
                return self._send_json(core.load_settings())
            if path == "/api/health":
                return self._send_json(core.health_check())
            if path == "/api/maintenance":
                return self._send_json(core.maintenance_status())
            if path == "/api/bios":
                return self._send_json(core.bios_recommendations())
            if path == "/api/hardware-profile":
                return self._send_json(core.hardware_profile(bool(urlparse(self.path).query)))
            if path == "/api/logon-autoapply":
                import azor_autostart
                return self._send_json({"ok": True, **azor_autostart.status(core)})
            if path == "/api/mode-cleanup":
                from azor_modules.engine import mode_cleanup_candidates
                return self._send_json({"ok": True, "items": mode_cleanup_candidates()})
            if path == "/api/usb-irq":
                # Mede de verdade (2 s de contador) e le o registro; so sob demanda,
                # na tela do controle.
                return self._send_json({"ok": True, "state": core.usb_interrupt_affinity_state(force=True),
                                        "load": core.interrupt_load_by_cpu(2.0)})
            if path == "/api/analyze":
                query = parse_qs(urlparse(self.path).query)
                profile = str((query.get("profile") or ["auto"])[0])
                return self._send_json({"items": core.analyze_optimizations(profile), "profile": profile})
            if path == "/api/modules":
                from azor_modules.engine import module_manifest
                return self._send_json({"engine": core.optimization_engine_status("auto"), "modules": module_manifest()})
            if path == "/api/optimization-plan":
                from azor_modules.engine import build_plan
                query = parse_qs(urlparse(self.path).query)
                profile = str((query.get("profile") or ["auto"])[0])
                return self._send_json(build_plan(profile))
            if path == "/api/power-guard":
                force = "force" in parse_qs(urlparse(self.path).query)
                data = power_guard.diagnose(force)
                data["persistence_test"] = power_guard.persistence_test_check()
                return self._send_json(data)
            if path == "/api/optimization-simulate":
                query = parse_qs(urlparse(self.path).query)
                profile = str((query.get("profile") or ["auto"])[0])
                return self._send_json(core.simulate_optimizations(profile))
            if path == "/api/restore-points":
                return self._send_json({
                    "snapshots": core.list_snapshots(),
                    "baseline": bool(core.BASELINE_FILE.exists()),
                    "windows_protection": core.system_protection_status(),
                    "revertible": core.revertible_optimizations(),
                })
            if path == "/api/journal":
                query = parse_qs(urlparse(self.path).query)
                limit = int((query.get("limit") or ["300"])[0] or 300)
                return self._send_json({"rows": core.read_journal(limit)})
            if path == "/api/bottleneck":
                force = "force" in parse_qs(urlparse(self.path).query)
                return self._send_json(core.bottleneck_report(force))
            if path == "/api/stutter":
                return self._send_json(core.stutter_diagnosis())
            if path == "/api/game-diagnostic":
                return self._send_json(game_diag.status())
            if path == "/api/game-diagnostic/reports":
                return self._send_json(game_diag.list_reports())
            if path == "/api/input-live":
                # The polling fallback has to be able to stand on its own, so it
                # starts the listener too. start() is idempotent and both calls
                # refresh the heartbeat that keeps the watchdog from stopping it.
                input_monitor.start()
                return self._send_json(input_monitor.snapshot())
            if path == "/api/input-live/stream":
                return self._stream_input_live()
            if path == "/api/gamepad-live":
                # A aba Controle pede isto algumas vezes por segundo; cada pedido
                # renova o vigia, e sem pedido a coleta do XInput para sozinha.
                return self._send_json(gamepad_monitor.snapshot())
            if path == "/api/hardware-center":
                force = "force" in parse_qs(urlparse(self.path).query)
                return self._send_json(core.hardware_command_center(force))
            if path == "/api/storage-health":
                force = "force" in parse_qs(urlparse(self.path).query)
                return self._send_json(core.storage_health(force))
            if path == "/api/drivers":
                force = "force" in parse_qs(urlparse(self.path).query)
                return self._send_json(core.driver_inventory(force))
            if path == "/api/startup":
                return self._send_json(core.startup_items())
            if path == "/api/bios-copilot":
                return self._send_json(core.bios_copilot())
            if path == "/api/thermal":
                return self._send_json(core.thermal_snapshot())
            if path == "/api/action-plan":
                query = parse_qs(urlparse(self.path).query)
                return self._send_json(core.action_plan(str((query.get("profile") or ["auto"])[0])))
            if path == "/api/admin-gap":
                # Quantos ajustes do catalogo estao fora do alcance por falta de
                # elevacao. Contado do catalogo, nunca fixo no codigo.
                want = parse_qs(urlparse(self.path).query)
                return self._send_json(core.admin_blocked_tweaks(
                    (want.get("profile") or ["competitive"])[0]))
            if path == "/api/input-capabilities":
                return self._send_json({"kinds": core.input_capabilities(),
                                        "remap": core.controller_remap()})
            if path == "/api/driver-guide":
                return self._send_json(core.driver_guide())
            if path == "/api/drift":
                return self._send_json(core.drift_report())
            if path == "/api/firmware":
                return self._send_json(core.firmware_boot_status())
            if path == "/api/startup-report":
                return self._send_json(core.startup_report())
            if path == "/api/desired-state":
                return self._send_json({"state": core.desired_state(),
                                        "check": core.reconcile_desired_state(dry_run=True)})
            if path == "/api/azor-index":
                # TTL curto vive no proprio core; aqui so o force explicito repassa.
                return self._send_json(core.azor_index("force" in parse_qs(urlparse(self.path).query)))
            if path == "/api/arsenal":
                query = parse_qs(urlparse(self.path).query)
                return self._send_json(core.arsenal_snapshot(str((query.get("profile") or ["auto"])[0])))
            if path == "/api/azor-windows":
                return self._send_json(core.azor_windows_engine_status())
            if path == "/api/windows":
                return self._send_json({"game_mode": core.verify_game_mode(), "game_dvr_off": core.verify_game_dvr_off(), "power_schemes": core.list_power_schemes(), "active_power": core.get_active_power_scheme()})
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except Exception as e:
            core.log(f"GET {path} error: {e}")
            return self._send_json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        # Idempotent job lookup remains available while its worker holds the
        # mutation lock. New jobs are serialized by JobManager itself.
        if urlparse(self.path).path == '/api/operations':
            return self._do_post_locked()
        if not ACTION_LOCK.acquire(blocking=False):
            return self._send_json({'ok':False,'error':'Outra operação está em andamento. Aguarde.'},409)
        try:
            return self._do_post_locked()
        finally:
            ACTION_LOCK.release()

    def _do_post_locked(self):
        path = urlparse(self.path).path
        if not self._same_origin():
            return self._reject("Requisicao de origem externa recusada.")
        if path.startswith("/api/") and self.headers.get(TOKEN_HEADER) != SESSION_TOKEN:
            return self._reject("Token de sessao ausente ou invalido.")
        data = self._body()
        try:
            if path == '/api/operations':
                name=str(data.get('name') or '')
                profile=str(data.get('profile') or 'safe')
                if name!='full_optimize' or profile not in ('safe','competitive','ultra','auto','campanha','stream','maximo','agressivo'):
                    return self._send_json({'ok':False,'error':'Operação ou perfil inválido.'},400)
                try:
                    job=JOBS.submit(name,profile,str(data.get('request_key') or ''),lambda progress:run_operation(core,{'operation':'full_optimize','profile':profile},progress))
                except BusyError as exc:
                    return self._send_json({'ok':False,'error':str(exc)},409)
                except ValueError as exc:
                    return self._send_json({'ok':False,'error':str(exc)},400)
                return self._send_json({'ok':True,'job':job},202)
            if path == '/api/mode-cleanup':
                # A lista sai do servidor, nao do pedido: a pagina so diz "desfazer".
                from azor_modules.engine import mode_cleanup_candidates
                ids=[row['id'] for row in mode_cleanup_candidates()]
                if not ids:
                    return self._send_json({'ok':True,'results':[],'detail':'Nada para desfazer.'})
                return self._send_json(run_operation(core,{'operation':'revert_tasks','ids':ids}))
            if path == '/api/logon-autoapply':
                enabled=data.get('enabled')
                profile=str(data.get('profile') or core.load_settings().get('performance_mode') or 'maximo')
                if not isinstance(enabled,bool) or profile not in ('maximo','agressivo'):
                    return self._send_json({'ok':False,'error':'Pedido inválido.'},400)
                return self._send_json(run_operation(core,{'operation':'logon_autoapply','enabled':enabled,'profile':profile}))
            if path == '/api/transactions/restore':
                return self._send_json(run_operation(core,{'operation':'restore_transaction','id':str(data.get('id') or '')}))
            if path == '/api/power-control':
                operation=data.get('operation')
                if operation not in ('power_plan','power_cpu'):return self._send_json({'ok':False,'error':'Operação de energia inválida.'},400)
                return self._send_json(run_operation(core,{**data,'operation':operation}))
            if path == '/api/service-control':
                return self._send_json(run_operation(core,{**data,'operation':'service'}))
            if path == '/api/game-mode':
                operation=data.get('operation')
                if operation=='configure':
                    return self._send_json(core.GAME_PRIORITY.configure(data.get('profiles'),data.get('background',[])))
                if operation not in ('start','stop'):return self._send_json({'ok':False,'error':'Operação inválida.'},400)
                ok,detail=getattr(core.GAME_PRIORITY,operation)()
                return self._send_json({'ok':ok,'detail':detail})
            if path == "/api/action":
                return self._send_json(do_action(str(data.get("name") or ""), data))
            if path == "/api/measure-sleep":
                result = core.measure_sleep(float(data.get("interval_ms", 1.0)), int(data.get("iterations", 80)))
                return self._send_json({"ok": True, "result": result})
            if path == "/api/measure-precision":
                result = core.measure_precision(float(data.get("interval_ms", 1.0)), int(data.get("iterations", 240)))
                return self._send_json({"ok": True, "result": result})
            if path == "/api/ping":
                host = str(data.get("host") or "1.1.1.1")
                return self._send_json(core.ping_test(host))
            if path == "/api/game-diagnostic/start":
                return self._send_json(game_diag.start(str(data.get("label") or "antes"), str(data.get("customer") or "")))
            if path == "/api/game-diagnostic/stop":
                return self._send_json(game_diag.stop())
            if path == "/api/game-diagnostic/setup-frame-capture":
                return self._send_json(game_diag.setup_frame_capture())
            if path == "/api/bios-checklist":
                return self._send_json(core.set_bios_checklist(str(data.get("key") or ""), bool(data.get("done"))))
            if path == "/api/settings":
                settings = core.load_settings()
                for key in ["mode", "animations", "accent", "start_with_windows", "notifications", "language", "show_tips", "monitor_interval", "guardian_enabled", "game_monitor_enabled", "daily_maintenance_enabled", "daily_maintenance_hour", "islc_autostart", "islc_watchdog", "islc_game_only", "persistent_game_mode", "persistent_game_dvr_off", "persistent_power_profile", "power_enforcement", "power_enforcement_game_only", "safe_windows_cleanup", "auto_start_agent", "pause_3d_when_game", "guardian_watchdog_task", "persistent_windows_suggestions_off", "persistent_transparency_off", "persistent_widgets_hidden", "islc_start_minimized", "latency_engine_autostart", "latency_engine_game_only", "latency_target_ms", "desktop_shortcut", "apply_azor_wallpaper", "input_lab_profiles", "start_minimized", "game_priority_engine", "controller_remap", "performance_mode"]:
                    if key in data:
                        settings[key] = data[key]
                if settings.get("performance_mode") not in ("maximo", "agressivo"):
                    settings["performance_mode"] = "maximo"
                # "Iniciar com o Windows" deixou de ser zerado aqui.
                #
                # A linha antiga era `settings["start_with_windows"] = False`, de
                # quando o app se copiava sozinho e criava VBS e tarefa agendada.
                # Nada disso existe mais: hoje e UMA entrada em HKCU\...\Run
                # apontando para o launcher que ja esta na pasta.
                #
                # Enquanto essa linha existiu, o interruptor da tela era inutil -
                # o servidor apagava a escolha do cliente a cada salvamento. E
                # sem o app subindo no boot, o Memory Engine, o timer e a
                # prioridade do jogo tambem nao eram permanentes: eles vivem
                # dentro do processo.
                if "start_with_windows" in data:
                    quer = bool(data["start_with_windows"])
                    ok_sw, det_sw = core.set_start_with_windows(quer)
                    # O registro e a verdade: se a gravacao nao confirmou, a
                    # preferencia guardada acompanha o que REALMENTE esta la.
                    settings["start_with_windows"] = core.get_start_with_windows()
                    startup_result = {"name": "Iniciar com o Windows",
                                      "ok": ok_sw, "detail": det_sw}
                else:
                    settings["start_with_windows"] = core.get_start_with_windows()
                    startup_result = None
                settings["guardian_watchdog_task"] = False
                settings["daily_maintenance_enabled"] = False
                # Power policy is intentionally fixed: the app owns and verifies AZOR FPS BOOST.
                core.save_settings(settings)
                apply_results=[]
                if startup_result:
                    apply_results.append(startup_result)
                # `validate` separa duas coisas que antes eram a mesma: guardar a
                # preferencia (barato, acontece a cada clique agora que a tela
                # salva sozinha) e reaplicar o plano de energia (powercfg, caro).
                # Sem esta separacao, arrastar um controle deslizante abria um
                # processo powercfg por movimento.
                if core.is_windows() and bool(data.get("validate")):
                    state=core.azor_fps_boost_power_status()
                    apply_results.append({"name":"Plano de energia","ok":True,"detail":"Leitura concluída. Nenhum plano foi aplicado.","state":state})
                    if "latency_engine_autostart" in data and not bool(data["latency_engine_autostart"]):
                        ok,detail=core.TIMER_SESSION.disable(); apply_results.append({"name":"Latency Engine UI process","ok":ok,"detail":detail})
                return self._send_json({"ok": all(x.get("ok") for x in apply_results) if apply_results else True, "settings": settings, "apply_results": apply_results})
            return self._send_json({"ok": False, "error": "endpoint not found"}, 404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except Exception as e:
            core.log(f"POST {path} error: {e}\n{traceback.format_exc()}")
            return self._send_json({"ok": False, "error": str(e)}, 500)


def run_self_test():
    checks = []
    def add(name, ok, detail=''):
        checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    required = [WEB/'index.html', WEB/'app.js', WEB/'styles.css', WEB/'assets'/'Azor_icon.png', WEB/'assets'/'wallpaper_azor_1920x1080.png']
    for p in required:
        add('file:'+p.name, p.is_file() and p.stat().st_size > 0, p)
    app_text = (WEB/'app.js').read_text(encoding='utf-8', errors='replace') if (WEB/'app.js').exists() else ''
    # 'function hexRgb' in app_text passava ate com o corpo virando `return null`.
    # Quem guarda isso agora e aux:hexRgb no self-test do navegador, que CHAMA a
    # funcao e exige um rgb valido de volta.
    add('device_hexRgb_helper', "['aux:hexRgb'" in app_text,
        'coberto por chamada real no AzorUiSelfTest')
    add('accent_helper', 'function applyAccent' in app_text, 'Required during summary/settings refresh')
    add('profile_label_helper', "['aux:profileLabel'" in app_text,
        'coberto por chamada real no AzorUiSelfTest (confere SEGURO e AZOR ULTRA)')
    add('route_keyboardmouse', 'keyboardmouse:renderKeyboardMouse' in app_text)
    add('route_controller', 'controller:renderController' in app_text)
    route_functions = [
        'renderHome','renderQuick','renderAdvanced','renderFortnite','renderDevice','renderKeyboardMouse','renderController',
        'renderMonitor','renderGameDiagnostic','renderStutter','renderWindows','renderGuardian','renderMaintenance','renderBios','renderNetwork',
        'renderLatency','renderRestore','renderLogs','renderSettings'
    ]
    for fn in route_functions:
        add('ui_route:'+fn, ('function '+fn) in app_text, 'Required by sidebar route map')
    add('input_lab_ui', 'AZOR INPUT LAB' in app_text and 'simple-input-section' in app_text and 'premium2d' in app_text and 'function input2DStage' in app_text)
    add('input_lab_guided_presets', 'INPUT_PRESETS' in app_text and 'data-input-preset' in app_text and 'advancedInput' in app_text)
    add('input_lab_accessible_choices', 'preset-recommended' in app_text and 'aria-pressed' in app_text and 'role="switch"' in app_text and 'inputOptionLabel' in app_text)
    add('ui_selftest_hook', 'function uiSelfTest' in app_text)
    css_text = (WEB/'styles.css').read_text(encoding='utf-8', errors='replace') if (WEB/'styles.css').exists() else ''
    source = Path(__file__).read_text(encoding='utf-8', errors='replace')
    add('device_multi_provider_detection', 'Win32_Keyboard' in Path(ROOT/'azor_core.py').read_text(encoding='utf-8', errors='replace') and 'Win32_PointingDevice' in Path(ROOT/'azor_core.py').read_text(encoding='utf-8', errors='replace'))
    add('device_api', '/api/devices' in Path(__file__).read_text(encoding='utf-8', errors='replace'))
    add('input_lab_api', '/api/input-lab' in Path(__file__).read_text(encoding='utf-8', errors='replace'))
    add('game_diagnostic_api', '/api/game-diagnostic' in Path(__file__).read_text(encoding='utf-8', errors='replace') and 'import azor_game_diag as game_diag' in Path(__file__).read_text(encoding='utf-8', errors='replace'))
    add('input_2d_svg_visuals', all(x in app_text for x in ['function controllerSvg','function mouseSvg','function keyboardSvg']))
    add('input_2d_live_feedback', 'function bindLiveInputOnce' in app_text and 'function pollGamepadVisual' in app_text and 'data-live-kind' in app_text)
    add('input_2d_css', 'premium2d' in css_text and 'input2d-stage' in css_text and 'live-active' in css_text)
    core_text = Path(ROOT/'azor_core.py').read_text(encoding='utf-8', errors='replace')
    engine_path = ROOT/'azor_modules'/'engine.py'
    engine_text = engine_path.read_text(encoding='utf-8', errors='replace') if engine_path.exists() else ''
    module_files = ['__init__.py','base.py','engine.py','registry.py','power.py','gpu.py','fortnite.py','maintenance.py','network.py','input_usb.py','hardware.py','services.py','memory.py']
    for mod_name in module_files:
        mod_path = ROOT/'azor_modules'/mod_name
        add('module:'+mod_name, mod_path.is_file() and mod_path.stat().st_size > 0, mod_path)
    add('modular_engine_facade', 'from azor_modules.engine import execute' in core_text and 'optimization_engine_status' in core_text)
    add('modular_engine_manifest', 'def module_manifest' in engine_text and 'MODULES =' in engine_text)
    add('modular_engine_plan', 'def build_plan' in engine_text and 'eligible_count' in engine_text)
    add('modular_engine_verify', 'task.verify' in engine_text and 'task.compatible' in engine_text)
    try:
        import ast, collections
        tree=ast.parse(core_text); names=collections.defaultdict(list)
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): names[node.name].append(node.lineno)
        dupes={k:v for k,v in names.items() if len(v)>1}
        add('no_duplicate_top_level_functions', not dupes, dupes)
    except Exception as e:
        add('no_duplicate_top_level_functions', False, e)
    add('restore_tracks_mouse_keyboard', all(x in core_text for x in ['MouseThreshold1', 'MouseThreshold2', 'KeyboardDelay', 'KeyboardSpeed']))
    add('restore_tracks_usb_power', 'usb_selective_suspend' in core_text and '_set_usb_selective_suspend_indexes' in core_text)
    add('fortnite_preset_reread_verify', 'Fortnite preset verification failed' in core_text and 'reread = path.read_text' in core_text)
    add('fortnite_backup_hash_verify', 'failed byte-for-byte verification' in core_text)
    add('snapshot_hard_gate', 'Nenhuma otimização foi aplicada' in engine_text and 'snapshot_ok' in engine_text)
    add('input_profile_truth_counts', all(x in core_text for x in ['applied_verified', 'profile_only', 'failed']))
    add('quick_mode_selected_ui', 'aria-checked' in app_text and 'SELECIONADO' in app_text and 'selected-mode-banner' in app_text)
    # O papel de parede com o logo saiu do fundo no redesign de 09/2026: com
    # `background-attachment: fixed` ele repintava a janela inteira a cada rolagem,
    # e um logo de 700 px atras dos cartoes competia com o texto. O arquivo continua
    # em assets/ (esta na lista de obrigatorios acima); a marca na tela e o icone.
    add('azor_real_brand_assets', 'assets/Azor_icon.png' in (WEB/'index.html').read_text(encoding='utf-8', errors='replace')
        and 'fixed no-repeat' not in css_text,
        'fundo fixo de tela cheia repinta a janela a cada rolagem')
    add('game_only_latency_policy', 'latency_engine_game_only' in core_text and 'timer_should_run' in (ROOT/'azor_agent.py').read_text(encoding='utf-8', errors='replace'))
    index_text = (WEB/'index.html').read_text(encoding='utf-8', errors='replace') if (WEB/'index.html').exists() else ''
    add('input_2d_no_webgl_dependency', 'azor3d.js' not in index_text and '3D INTERATIVO' not in app_text)
    add('input_2d_only_assets', not (WEB/'azor3d.js').exists() and not (WEB/'models').exists())
    add('input_2d_live_badge', '2D AO VIVO' in app_text and 'premium2d' in app_text)
    add('controller_filter_rejects_ahci', not core._looks_like_game_controller('Controlador AHCI SATA Padrão','HDC','PCI\\VEN_8086&CC_0106'))
    add('controller_filter_accepts_xbox', core._looks_like_game_controller('Xbox Wireless Controller','HIDClass','HID\\VID_045E&PID_0B13'))
    add('runtime_declares_2d_ui', '"ui_mode": "2d"' in source and 'ui_fingerprint' in source)
    main_region = source[source.rfind('def main():'):]
    add('fresh_backend_each_launch', 'open_ui(existing)' not in main_region and 'Existing backend reused:' not in main_region)
    # --- invariantes introduzidos na auditoria de performance/seguranca -------
    add('ui_stops_polling_when_hidden',
        'visibilitychange' in app_text and 'stopPolling' in app_text,
        'a janela escondida atras do jogo nao pode continuar sondando')
    add('ui_requests_have_timeout',
        'AbortController' in app_text and 'API_TIMEOUT_MS' in app_text,
        'uma requisicao sem resposta travava o loop de polling para sempre')
    add('ui_backs_off_on_failure',
        'pollBackoff' in app_text and 'maxBackoff' in app_text)
    add('ui_recovers_session_token',
        'refreshAzorToken' in app_text,
        'o backend sorteia token novo a cada boot; a pagina aberta precisa se recuperar')
    add('ui_keeps_scroll_and_focus_on_render',
        'keptScroll' in app_text and 'keptFocus' in app_text,
        'o re-render do poll nao pode apagar o que esta sendo digitado')
    add('counter_animation_keeps_the_sign',
        'countPrefix' in app_text and 'countDecimals' in app_text,
        'a animacao reescrevia o texto sem o sinal: -4.2% (melhorou) e +4.2% (piorou) viravam 4%')
    add('ui_counters_animate_on_arrival_only',
        'lastAnimatedPage' in app_text,
        'senao todo numero da tela volta a zero uma vez por tick')
    add('api_rejects_foreign_origin',
        '_same_origin' in source and 'Sec-Fetch-Site' in source and 'LOCAL_HOSTS' in source)
    add('api_requires_token_on_post',
        'TOKEN_HEADER' in source and 'SESSION_TOKEN' in source and 'azor-token' in source)
    add('api_sets_security_headers',
        'Content-Security-Policy' in source and 'X-Content-Type-Options' in source)
    add('monitor_sampling_is_backgrounded',
        'MONITOR_SAMPLER' in core_text and '_MonitorSampler' in core_text,
        'GET /api/monitor nao pode abrir processo dentro da requisicao')
    add('monitor_sampler_stops_when_idle',
        'IDLE_GRACE' in core_text,
        'sem ninguem olhando, a coleta tem de parar sozinha')
    add('gpu_feed_dies_with_the_app',
        'JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE' in core_text and '_adopt_child' in core_text,
        'o launcher mata o backend a forca; o filho nao pode sobreviver a isso')
    add('gpu_feed_orphans_are_swept',
        'sweep_orphan_gpu_feeds' in core_text and 'sweep_orphan_gpu_feeds' in source)
    add('nvidia_feed_is_single_process',
        '_NvidiaFeed' in core_text and '-lms' in core_text)
    add('summary_reads_through_ttl_cache',
        'cached_reading' in core_text and 'invalidate_cache' in core_text)
    add('actions_invalidate_cached_readings',
        'core.invalidate_cache()' in source and 'READ_ONLY_ACTIONS' in source,
        'a tela nao pode mostrar o estado anterior ao proprio clique do usuario')
    add('devices_are_cached_with_force',
        'DEVICE_CACHE_TTL' in core_text and 'def detect_devices(force' in core_text)
    add('devices_collapse_duplicates',
        '_collapse_duplicate_devices' in core_text,
        'o mesmo hardware nao pode ser contado uma vez por colecao HID')
    add('bottleneck_detector',
        'bottleneck_report' in core_text and '/api/bottleneck' in source)
    add('bottleneck_reads_display_refresh',
        'EnumDisplaySettingsW' in core_text,
        'monitor abaixo da taxa maxima e FPS de graca')
    add('bottleneck_reads_memory_config',
        'ConfiguredClockSpeed' in core_text,
        'XMP/EXPO desligado costuma ser o maior item isolado')
    add('bottleneck_does_not_guess_live_limit',
        'live_note' in core_text,
        'veredito de carga exige o jogo aberto; o app tem de dizer isso')
    add('sensor_probe_backs_off',
        '_MON_HW_TTL_MAX' in core_text,
        'sem LHM/OHM instalado a sonda custava 14 s de CPU por minuto')
    add('static_cache_disabled', 'def end_headers(self):' in source and 'no-store, no-cache, must-revalidate' in source)
    launcher = (ROOT.parent/'AZOR Optimization.bat').read_text(encoding='utf-8', errors='replace') if (ROOT.parent/'AZOR Optimization.bat').exists() else ''
    add('launcher_closes_legacy_azor', r'azor_server\.py|azor_agent\.py' in launcher and "edge_profile" in launcher and 'Stop-Process' in launcher)
    add('launcher_removes_legacy_engine_only', "Join-Path $home 'app'" in launcher and "Join-Path $home 'runtime'" in launcher and "Join-Path $home 'user'" not in launcher)
    add('launcher_refreshes_desktop_shortcut', 'AZOR Optimization.lnk' in launcher and "$s.TargetPath='%~f0'" in launcher)
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.bind(('127.0.0.1',0));s.close();add('localhost_bind',True)
    except Exception as e:
        add('localhost_bind',False,e)
    add('fortnite_resolution_verified_action', 'set_fortnite_resolution_quality' in core_text and 'fortnite_res_85' in source)
    # O check antes exigia a linha exata do menu lateral. O menu passou de 12
    # destinos para 5 e a latencia virou aba do agrupador Maquina - a funcao
    # continua inteira, o literal e que morreu. Verificar alcancabilidade, nao
    # texto de menu: um check preso a cosmetico reprova toda faxina de UI.
    add('unified_latency_lab',
        "['latency','Latência & ISLC']" in app_text
        and 'runLatencyOptimize' in app_text and 'latencyBaseline' in app_text
        and 'latency:renderLatency' in app_text)
    add('latency_comparison_real_endpoint', '/api/measure-sleep' in source and "name:'timer_half'" in app_text)
    add('production_readiness_strip',
        "['aux:verifiedReadiness'" in app_text and 'readiness-strip' in css_text,
        'coberto por chamada real: o score tem de cair dentro de 0..100')
    add('quick_post_apply_reanalysis', 'S.lastQuickResult=r' in app_text and "/api/analyze?profile=" in app_text)
    add('latency_five_pass_median', 'rodada ${i+1}/5' in app_text and 'stability_pct' in app_text and 'latencyConfidence' in app_text)
    add('precision_measurement_ui_quiet', "S.page==='latency'&&!S.latencyOptimizing&&!S.competitiveSessionRunning" in app_text)
    add('client_sidebar_reduced', "['gameDiag','◎','Diagnóstico em Jogo']" not in app_text and "['windows','⊞','Windows & Sistema']" not in app_text)
    add('no_fake_latency_claims', 'números falsos' not in app_text.lower() and 'não é ganho de fps' in app_text.lower() and 'não representa input lag direto' in app_text.lower())
    add('maximum_power_verified_action', 'set_azor_fps_boost_power' in core_text and 'azor_fps_boost_power_status' in core_text and '"power_max"' in source)
    add('azor_fps_boost_owned_plan', 'AZOR_POWER_NAME = "AZOR FPS BOOST"' in core_text and 'ensure_azor_fps_boost_scheme' in core_text and '/changename' in core_text)
    add('azor_fps_boost_no_high_fallback', 'High Performance fallback' not in core_text and 'return set_azor_fps_boost_power()' in core_text)
    add('simplified_sidebar', "['advanced','⌘','Otimização Avançada']" not in app_text and "['measure','◷','Measure Sleep']" not in app_text)
    add('hardware_auto_profile', 'def hardware_profile' in core_text and 'requested_profile' in engine_text and 'resolved_profile' in engine_text)
    add('hardware_report_export', 'def export_system_report' in core_text and '"export_report"' in source)
    add('runtime_health_endpoint', 'path == "/api/runtime"' in source)
    add('modular_engine_endpoints', 'path == "/api/modules"' in source and 'path == "/api/optimization-plan"' in source)
    open_region = source[source.find('def open_ui'):source.find('def main')]
    add('edge_does_not_shutdown_server', '.wait()' not in open_region and '.shutdown()' not in open_region)
    add('direct_ephemeral_bind', 'ThreadingHTTPServer(("127.0.0.1", bind_port), Handler)' in source)
    add('edge_build_isolated_profile', 'edge_current_2d_' in source and '--new-window' in source)

    # ---------- AZOR Windows bridge ----------
    # These constants were referenced but never defined, so every /api/windows
    # button raised NameError. Guard the definitions, not just the usage.
    for const in ('AZOR_WINDOWS_ROOT','AZOR_WINDOWS_CLI','AZOR_WINDOWS_STATE','AZOR_WINDOWS_VERIFY','AZOR_WINDOWS_HARDWARE','AZOR_WINDOWS_STORAGE'):
        add('azor_windows_const:'+const, hasattr(core, const), 'referenced by azor_windows_engine_status/command')
    add('azor_windows_status_no_nameerror', callable(getattr(core,'azor_windows_engine_status',None)) and isinstance(core.azor_windows_engine_status(), dict))
    add('azor_windows_reads_contract', 'AppContract.json' in core_text and 'utf-8-sig' in core_text, 'PowerShell writes UTF-8 with BOM')
    add('azor_windows_command_whitelist', 'allowed = set(AZOR_WINDOWS_COMMANDS)' in core_text and all(c in core_text for c in ('"Daily"','"GamePrep"','"StorageAnalyze"')))
    add('azor_windows_invalid_rejected', core.azor_windows_command('DefinitelyNotACommand').get('ok') is False)

    # ---------- Campaign profile ----------
    from azor_modules.base import PROFILES as _PROFILES
    # Contar perfis fixava o numero em 4 e reprovou a chegada do AZOR ULTRA. O
    # que importa e que nenhum perfil tenha SUMIDO - o Ultra somou, nao trocou.
    add('campaign_profile_registered',
        all(p in _PROFILES for p in ('safe', 'competitive', 'campanha', 'stream')))
    try:
        from azor_modules.engine import _all_tasks as _t
        _tasks = list(_t())
        _ultra = sum(1 for x in _tasks if x.supports_profile('ultra'))
        _comp = sum(1 for x in _tasks if x.supports_profile('competitive'))
        # O nivel mais alto nunca pode aplicar MENOS que o de baixo. Se alguem
        # esquecer "ultra" numa tarefa nova, este check pega.
        add('ultra_never_applies_less_than_competitive', _ultra >= _comp and _ultra > 0,
            f'ultra={_ultra} competitivo={_comp}')
        add('ultra_difference_is_the_session_engines',
            'latency_engine_game_only' in core_text
            and 'ULTRA - Timer sempre ativo' in core_text,
            'o Ultra aplica o MESMO catalogo; a diferenca sao os motores, e isso '
            'precisa estar no codigo e dito na tela')
        add('ultra_is_honest_about_being_the_same_catalog',
            'Mesmos ajustes + motores sempre ativos' in app_text,
            'ninguem pode comprar Ultra achando que sao mais tweaks')
    except Exception as _e:
        add('ultra_profile_contract', False, _e)
    add('campaign_profile_accepted_by_engine', 'set(PROFILES)' in engine_text)
    try:
        from azor_modules.engine import build_plan as _bp
        _camp = _bp('campanha'); _comp = _bp('competitive')
        _camp_ids = {t['id'] for t in _camp['tasks'] if 'campanha' in t['profiles']}
        add('campaign_resolves', _camp['resolved_profile'] == 'campanha')
        # The campaign profile must not be a copy of competitive: story players
        # keep their capture and their visual fidelity.
        add('campaign_keeps_capture', 'game_dvr' not in _camp_ids)
        add('campaign_keeps_visual_effects', 'visual_effects' not in _camp_ids)
        add('campaign_is_not_competitive', _camp_ids != {t['id'] for t in _comp['tasks'] if 'competitive' in t['profiles']})
        add('campaign_covers_stability', {'power_plan','automatic_pagefile','azor_memory_engine'} <= _camp_ids)
    except Exception as e:
        add('campaign_plan_builds', False, e)

    # ---------- Reversibilidade e baseline (auditoria Fase 0/1) ----------
    # Cada um destes ja custou caro uma vez, entao vira teste em vez de intencao.

    # O baseline e a unica copia de como o PC era antes do AZOR. Rodar a
    # otimizacao duas vezes gravava o estado ja otimizado como "original", e
    # "restaurar padroes do Windows" passava a restaurar o proprio AZOR.
    add('baseline_is_written_once', 'def _write_baseline_once' in core_text and 'if BASELINE_FILE.exists():' in core_text,
        'o baseline nunca pode ser sobrescrito por um lote posterior')
    add('batch_snapshots_are_versioned', 'def _archive_snapshot' in core_text and 'SNAPSHOT_DIR' in core_text,
        'um segundo lote nao pode apagar o registro do primeiro')
    add('restore_defaults_to_baseline', 'def restore_all(progress: Optional[Callable[[str, str], None]] = None, target: str = "baseline")' in core_text,
        'restaurar padroes do Windows significa voltar ao estado anterior ao AZOR')
    add('windows_restore_point_is_a_separate_thing',
        'def create_windows_restore_point' in core_text and 'This is NOT a Windows restore point' in core_text,
        'snapshot proprio e ponto de restauracao do Windows nao podem ser vendidos como a mesma coisa')
    add('revert_never_guesses_defaults', 'Nada foi apagado por suposicao' in core_text,
        'sem baseline para a chave, o app informa em vez de inventar um padrao')
    add('journal_is_structured', 'def journal(' in core_text and 'JOURNAL_FILE' in core_text and '/api/journal' in source)
    add('api_exposes_revert_and_simulation',
        '"revert_task"' in source and '/api/optimization-simulate' in source and '/api/restore-points' in source)

    try:
        from azor_modules.engine import _all_tasks as _tasks, simulate as _sim, revert_task as _revert
        _all = _tasks()
        _no_source = [t.id for t in _all if not (t.source or '').strip()]
        _no_tradeoff = [t.id for t in _all if not (t.trade_off or '').strip()]
        add('every_tweak_cites_a_source', not _no_source, _no_source)
        add('every_tweak_declares_its_trade_off', not _no_tradeoff, _no_tradeoff)
        # Um tweak so pode dizer que e reversivel se existir codigo que o reverta.
        _lying = [t.id for t in _all if t.reversible and t.revert is None]
        add('reversible_means_there_is_a_revert', not _lying, _lying)
        _unknown = [t.id for t in _all if t.revert is None and t.reversible]
        add('irreversible_tweaks_say_so', not _unknown, 'apagar arquivo nao volta atras, e o motor precisa admitir isso')
        # Toda chave que um tweak escreve precisa estar no baseline, senao
        # "reverter" nao tem de onde tirar o valor original e o app estaria
        # prometendo uma reversao que nao pode cumprir.
        #
        # Isto e barato e existe porque a lista rastreada vive em DOIS lugares
        # do azor_core (a definicao e um append 2000 linhas depois). Hoje as duas
        # batem; sem este check, a proxima chave adicionada a um tweak pode nao
        # bater, e ninguem descobriria ate um usuario tentar reverter.
        # A lista rastreada deixou de ser escrita a mao: ela e a uniao das chaves
        # declaradas por todos os modulos mais as por-maquina. Este check confere o
        # resultado da derivacao - se um modulo declarar uma chave que a captura nao
        # cobre, "reverter" ficaria sem valor de origem e o app estaria prometendo
        # uma reversao que nao pode cumprir.
        from azor_modules import engine as _eng
        _tracked = {(r, p.casefold(), n.casefold()) for r, p, n in core.tracked_registry()}
        _declared = [(mod, tid, entry)
                     for mod in _eng.MODULES
                     for tid, entries in (getattr(mod, 'KEYS', {}) or {}).items()
                     for entry in entries]
        _uncovered = [f'{tid}:{entry[2]}' for _mod, tid, entry in _declared
                      if (entry[0], entry[1].casefold(), entry[2].casefold()) not in _tracked]
        add('every_written_key_is_in_the_baseline', not _uncovered, _uncovered)
        add('baseline_is_derived_from_the_catalog',
            'def tracked_registry' in core_text and 'for root, path, name in tracked_registry():' in core_text
            and '_module_declared_registry_keys' in core_text,
            'a captura sai do catalogo; duas listas escritas a mao ja divergiram uma vez')
        add('catalog_declares_keys_for_every_module', len(_declared) >= 20, len(_declared))

        # Um tweak que reduz seguranca ou cujo resultado varia por maquina nao pode
        # entrar no botao de um clique. Ele existe, e reversivel e esta documentado -
        # mas quem liga e o usuario, num clique proprio.
        _auto_risky = [t.id for t in _all if t.risk in ('high', 'experimental') and t.automatic]
        add('risky_tweaks_are_never_in_the_one_click', not _auto_risky, _auto_risky)
        _no_metric_experimental = [t.id for t in _all
                                   if t.risk == 'experimental' and 'ab-test' not in t.tags]
        add('experimental_tweaks_are_declared_as_ab_tests', not _no_metric_experimental,
            _no_metric_experimental)
        _security = next((t for t in _all if t.id == 'memory_integrity_off'), None)
        add('security_cost_is_stated_in_caps', _security is not None
            and 'MENOS PROTEGIDO' in (_security.trade_off or ''),
            'o item que desliga a Integridade de Memoria precisa dizer o preco sem eufemismo')
        _restart_missing = [t.id for t in _all
                            if t.id in ('hags', 'gpu_msi', 'memory_integrity_off') and not t.restart]
        add('reboot_dependent_tweaks_say_so', not _restart_missing, _restart_missing)
        _svc = [t.id for t in _all if t.module == 'services']
        add('services_are_not_disabled_in_bulk', len(_svc) <= 5, _svc)

        # Aplicacao individual: sem ela, os itens que nao entram no lote seriam
        # decoracao na tela.
        from azor_modules.engine import apply_task as _apply
        add('api_exposes_individual_apply',
            '"apply_task"' in source and 'def apply_task' in engine_text)
        add('apply_task_rejects_unknown_task', _apply('nao_existe_este_tweak').get('ok') is False)
        add('apply_task_keeps_the_snapshot_gate',
            'Nada foi alterado.' in engine_text and 'capture_restore_point(force=True)' in engine_text,
            'o clique individual passa pela mesma trava do lote')

        # O estado de cada tweak na tela vem do proprio verify(), nao de uma cadeia
        # de if/elif por id que a proxima adicao esqueceria de atualizar.
        add('arsenal_state_comes_from_the_tweak_itself',
            'def _current_state' in engine_text and 'task.verify(core, ctx)' in engine_text)
        add('revert_rejects_unknown_task', _revert('nao_existe_este_tweak').get('ok') is False)
        # O modo simulacao existe para responder "o que voce faria" sem ja ter feito.
        _before = core.STATE_FILE.stat().st_mtime if core.STATE_FILE.exists() else None
        _plan = _sim('competitive')
        _after = core.STATE_FILE.stat().st_mtime if core.STATE_FILE.exists() else None
        add('simulation_writes_nothing', _before == _after and _plan.get('simulated') is True,
            'o modo simulacao nao pode encostar no estado do sistema')
        add('simulation_lists_real_steps', isinstance(_plan.get('steps'), list) and len(_plan['steps']) == len(_all))
    except Exception as _e:
        add('tweak_metadata_contract', False, _e)

    # ---------- "Aplicou = fica": persistencia entre reinicios ----------
    #
    # O bug de origem, medido num PC real: as configuracoes diziam
    # persistent_game_mode=True e latency_engine_autostart=True, e depois de um
    # reinicio o Game Mode estava desligado e o timer em "off". O app anotava a
    # intencao do usuario e nunca voltava para conferir. Para o cliente isso e
    # simplesmente "reiniciei e perdi tudo".
    try:
        add('applied_tweaks_are_remembered',
            'core.mark_task_applied' in engine_text and 'def mark_task_applied' in core_text,
            'sem o livro de registro, a reconciliacao nao sabe o que reaplicar')
        add('revert_forgets_the_tweak',
            'core.unmark_task_applied' in engine_text,
            'desfazer tem de ser para sempre; senao a proxima abertura reaplica')
        add('startup_reconciles_what_windows_undid',
            'run_startup_reconcile' in source and 'def reconcile_desired_state' in core_text)
        add('session_engines_come_back_on_open',
            'def restore_session_engines' in core_text and 'latency_engine_autostart' in core_text,
            'timer e Memory Engine sao de sessao, mas precisam voltar na abertura seguinte')
        _before = core.desired_state()
        core.mark_task_applied('__selftest__', 'Teste', 'competitive')
        _marked = '__selftest__' in core.desired_task_ids()
        core.unmark_task_applied('__selftest__')
        _cleared = '__selftest__' not in core.desired_task_ids()
        add('desired_state_round_trip', _marked and _cleared)
        add('reconcile_can_answer_without_writing',
            core.reconcile_desired_state(dry_run=True).get('dry_run') is True,
            'a tela precisa poder mostrar o diagnostico antes de agir')
    except Exception as _e:
        add('desired_state_contract', False, _e)

    add('settings_save_without_a_button',
        'scheduleSettingsSave' in app_text and 'scheduleInputProfilesSave' in app_text,
        'o cliente que mexia num interruptor e fechava o app perdia a mudanca')
    add('autosave_does_not_reapply_the_power_plan',
        'bool(data.get("validate"))' in source,
        'sem isto, arrastar um controle deslizante abria um powercfg por movimento')

    # ---------- bandeja, BIOS e Fortnite ----------
    _tray_path = ROOT / 'azor_tray.py'
    _tray_text = _tray_path.read_text(encoding='utf-8', errors='replace') if _tray_path.exists() else ''
    add('tray_module_present', bool(_tray_text) and 'Shell_NotifyIconW' in _tray_text)
    add('tray_can_really_exit', 'Sair do AZOR' in _tray_text and 'on_exit' in _tray_text,
        'um app que so esconde a janela e nao oferece sair vira processo fantasma')
    add('tray_hides_minimized_window', 'SW_HIDE' in _tray_text and 'IsIconic' in _tray_text)
    add('tray_does_not_inject_into_edge', 'poll' in _tray_text.lower() and 'SetWindowsHookEx' not in _tray_text,
        'hook global em processo de terceiro e o que faz antivirus reclamar de otimizador')
    add('firmware_checks_uefi_before_rebooting',
        'def firmware_boot_status' in core_text and 'GetFirmwareType' in core_text
        and '"reboot_to_firmware"' in source)
    add('firmware_reboot_is_cancelable',
        'def abort_reboot' in core_text and '"abort_reboot"' in source,
        'agendar reinicio sem poder cancelar seria sequestrar o PC do cliente')
    add('fortnite_offers_the_dx11_argument',
        'data-copy="-d3d11"' in app_text and 'TENTE E CONFIRA' in app_text,
        'o argumento existe; o que a Epic tirou foi a opcao do menu')

    # ---------- Prova medida, reinicio e deriva ----------
    #
    # Todo tweak declara a metrica que deveria mover, e ate aqui nenhum media.
    # Metrica declarada e promessa; metrica medida e prova. Estes checks existem
    # para que a prova nao vire outra promessa.
    try:
        add('proof_only_where_it_can_measure',
            'PROVABLE_TAGS' in core_text and 'def task_is_provable' in core_text,
            'oferecer "provar" num tweak que move FPS seria prometer o que so o Monitor de Jogo entrega')
        _fps_task = next((t for t in _all if t.id == 'fortnite_gpu'), None)
        add('proof_refuses_fps_claims',
            _fps_task is not None and not core.task_is_provable(_fps_task),
            'FPS so se mede com o jogo aberto')
        _timer_task = next((t for t in _all if t.id == 'latency_timer'), None)
        add('proof_accepts_latency_tweaks',
            _timer_task is not None and core.task_is_provable(_timer_task))
        add('proof_verdict_comes_from_the_tail',
            'PRIMARY = ("p99_us", "p95_us")' in core_text,
            'o jogador sente a espera que estourou, nao o desvio-padrao')
        add('proof_declares_disagreement',
            '"disagreement"' in core_text and 'direcao contraria' in core_text,
            'metrica secundaria que contradiz o veredito aparece, nao some')
        add('proof_says_when_a_reboot_is_still_missing',
            'restart_note' in core_text and 'ainda nao mostra o efeito final' in core_text)

        # Reinicio: a frase "so vale depois de reiniciar" tinha de virar uma
        # confirmacao, nao ficar so no texto.
        add('restart_tweaks_are_confirmed_after_the_boot',
            'def confirm_after_reboot' in core_text and 'def boot_id' in core_text
            and 'core.mark_pending_reboot' in engine_text)
        add('reboot_confirmation_waits_for_an_actual_reboot',
            'entry.get("boot") == now_boot' in core_text,
            'cobrar confirmacao antes de o usuario reiniciar seria injusto')
        _restart_ids = {t.id for t in _all if t.restart}
        add('every_restart_tweak_enters_the_pending_ledger', len(_restart_ids) >= 10, len(_restart_ids))

        # Deriva: saber QUAL ajuste o Windows desfaz vale mais que o conserto.
        add('drift_is_recorded_and_capped',
            'def record_drift' in core_text and 'dates[-8:]' in core_text,
            'um log que cresce sem limite vira outro arquivo para ninguem ler')
        add('drift_is_visible_to_the_user',
            'driftBanner' in app_text and '/api/drift' in source)
        add('drift_blames_windows_not_the_app',
            'Nao e falha do app' in core_text or 'não é falha do app' in app_text.lower()
            or 'Não é falha do app' in app_text)

        # Relacoes entre tweaks.
        _with_rel = [t.id for t in _all if getattr(t, 'relations', ())]
        add('catalog_declares_tweak_interactions', len(_with_rel) >= 4, _with_rel)
        _bad_rel = [f"{t.id}->{r.get('id')}" for t in _all for r in (getattr(t, 'relations', ()) or [])
                    if r.get('id') not in {x.id for x in _all}]
        add('every_relation_points_to_a_real_tweak', not _bad_rel, _bad_rel)
        add('relations_are_resolved_with_name_and_state',
            'rel["applied"] = other["state"]' in engine_text,
            'um id cru na tela nao diz nada a quem nao leu o codigo')
    except Exception as _e:
        add('proof_and_drift_contract', False, _e)

    # Corpo de uma funcao pelo NOME, em vez de fatiar o arquivo por posicao: a
    # ordem das definicoes muda, e um check que depende dela quebra sozinho na
    # proxima faxina. Usado por varios invariantes abaixo.
    def _body_of(fn_name, text):
        start = text.index(f"def {fn_name}(")
        rest = text[start:]
        nxt = rest.find(chr(10) + "def ", 1)
        return rest[:nxt if nxt > 0 else len(rest)]

    # ---------- "Meu PC ficou lento para abrir programa" ----------
    #
    # O dono do projeto reportou o sintoma e a maquina dele tinha exatamente a
    # causa: SysMain parado e EnablePrefetcher = 0. Sao as duas pecas que fazem
    # o Windows pre-carregar o que voce usa todo dia.
    try:
        _lc = core.app_launch_cache_state()
        add('app_launch_cache_is_diagnosed',
            isinstance(_lc, dict) and "broken" in _lc and "prefetcher" in _lc,
            'sem ler SysMain e Prefetcher o app nao consegue explicar o sintoma mais comum')
        # _repair so e importado mais abaixo neste arquivo, e o reparo tem de ser
        # cobrado por COMPORTAMENTO: a funcao existe E esta chamavel, nao apenas
        # o nome dela aparece no texto - a catraca reprovou a primeira versao
        # deste check, que era exatamente o padrao decorativo que ela vigia.
        from azor_modules import repair as _rep_mod
        add('app_launch_cache_has_a_repair',
            'app_launch_cache_repair' in {t.id for t in _rep_mod.tasks()}
            and callable(getattr(core, 'repair_app_launch_cache', None)),
            'detectar sem consertar deixa o cliente sabendo do problema e sem saida')
        add('app_launch_repair_restores_the_windows_default',
            '"EnablePrefetcher", 3' in core_text and '"SysMain", "start=", "auto"' in core_text,
            '3 e o padrao do Windows (aplicativos + boot); auto e o inicio de fabrica do SysMain')
        add('app_launch_problem_is_a_high_finding',
            'parou de pré-carregar os programas' in core_text,
            'nenhum tweak de FPS compensa esperar a janela do navegador abrir')

        # A corrente da permanencia: app no boot -> agente -> Memory Engine,
        # timer e prioridade. Sem o primeiro elo, os tres nao sao permanentes.
        _save = _body_of('do_POST', source) if 'def do_POST' in source else source
        # Procurar em CODIGO, nao no arquivo inteiro: o comentario que explica
        # por que a linha saiu cita a propria linha, e a primeira versao deste
        # check reprovou por causa da propria documentacao. Terceira vez que essa
        # armadilha aparece no projeto - por isso agora ela desconta comentario.
        # Procurar a ATRIBUICAO como instrucao: uma linha que COMECA com ela.
        # O comentario acima cita a linha antiga, e a propria linha deste check
        # carrega o literal - as duas versoes anteriores reprovaram por isso.
        # Uma linha de codigo real comeca com `settings[`; as outras duas
        # comecam com `#` ou com aspas.
        _forced = [ln for ln in source.splitlines()
                   if ln.strip().startswith('settings["start_with_windows"] = False')]
        add('startup_preference_is_no_longer_forced_off',
            not _forced,
            'o servidor zerava a escolha do cliente a cada salvamento, e o interruptor '
            'da tela nunca tinha efeito')
        add('startup_preference_is_applied_not_just_stored',
            'core.set_start_with_windows(quer)' in source,
            'guardar no JSON nao cria a entrada no registro')
        add('startup_preference_trusts_the_registry',
            'settings["start_with_windows"] = core.get_start_with_windows()' in source,
            'se a gravacao nao confirmou, a preferencia guardada tem de acompanhar a realidade')
        add('startup_toggle_exists_on_screen',
            "'startupToggle'" in app_text and 'Abrir junto com o Windows' in app_text,
            'o codigo de salvar ja procurava startupToggle, mas o interruptor nao existia')
        add('settings_explain_what_stops_when_the_app_closes',
            'Memory Engine, o Timer e a Prioridade do jogo vivem dentro do aplicativo' in app_text,
            'o cliente precisa saber que esses tres param com o app fechado')
    except Exception as _e:
        add('app_launch_cache_contract', False, _e)

    # ---------- A suite testando a si mesma ----------
    #
    # Descobri escrevendo dois invariantes que nasceram decorativos: eles
    # procuravam 'def alguma_coisa' no texto do arquivo e continuavam passando
    # depois que eu arranquei a CHAMADA de dentro do app. Um check assim passa
    # ate se o corpo da funcao for `return None`.
    #
    # Medido no dia em que este bloco nasceu: 52 checks seguiam esse padrao.
    # Os dois blocos abaixo atacam o problema por dois lados - um converte os
    # que da para converter, o outro impede a suite de piorar.
    try:
        # 1. Chamar de verdade o que e seguro chamar.
        #
        # Estas sao funcoes de LEITURA: nao gravam registro, nao sobem processo,
        # nao pedem elevacao. Chamar cada uma e exigir uma forma coerente vale
        # mais que confirmar que o nome dela aparece no arquivo.
        _live = []

        def _probe(label, fn, shape):
            try:
                value = fn()
            except Exception as exc:
                _live.append((label, False, f"levantou {type(exc).__name__}: {exc}"))
                return
            ok = shape(value)
            _live.append((label, ok, f"devolveu {type(value).__name__}"))

        _probe('boot_id', core.boot_id, lambda v: isinstance(v, str) and len(v) > 0)
        _probe('is_windows_11', core.is_windows_11, lambda v: isinstance(v, bool))
        _probe('game_focused', core.game_focused,
               lambda v: isinstance(v, dict) and "focused" in v)
        _probe('get_start_with_windows', core.get_start_with_windows,
               lambda v: isinstance(v, bool))
        _probe('should_start_minimized', core.should_start_minimized,
               lambda v: isinstance(v, bool))
        _probe('tracked_registry', core.tracked_registry,
               lambda v: isinstance(v, list) and len(v) > 0
               and all(len(x) == 3 for x in v))
        _probe('_process_list', core._process_list,
               lambda v: isinstance(v, list) and len(v) > 0
               and all(isinstance(n, str) and isinstance(pid, int) for n, pid in v))
        _probe('cpu_topology', core.cpu_topology,
               lambda v: isinstance(v, dict) and "detail" in v)
        _probe('hardware_profile', core.hardware_profile,
               lambda v: isinstance(v, dict) and "label" in v)
        _probe('timer_global_scope', core.timer_global_scope,
               lambda v: isinstance(v, dict)
               and v.get("scope") in ("process", "pending", "system"))
        _probe('background_footprint', core.background_footprint,
               lambda v: isinstance(v, dict) and isinstance(v.get("suspended"), list))
        _probe('admin_blocked_tweaks', core.admin_blocked_tweaks,
               lambda v: isinstance(v, dict) and isinstance(v.get("total"), int))
        _probe('input_capabilities', core.input_capabilities,
               lambda v: isinstance(v, dict) and len(v) > 0)
        _probe('controller_remap', core.controller_remap,
               lambda v: isinstance(v, dict) and v.get("applied") is False)
        _probe('firmware_boot_status', core.firmware_boot_status,
               lambda v: isinstance(v, dict))

        for _label, _ok, _why in _live:
            add(f'live_{_label.strip("_")}_actually_returns_something', _ok, _why)

        # 2. A catraca.
        #
        # Conta o padrao decorativo e falha se ele CRESCER. Nao exige consertar
        # os 52 de uma vez - exige que ninguem adicione o 53o sem perceber.
        import re as _re
        _self_src = source[source.index('def run_self_test'):]
        _decor = (len(_re.findall(r"'function \w+' in app_text", _self_src))
                  + len(_re.findall(r"'def \w+' in core_text", _self_src)))
        # O teto e o valor MEDIDO agora, nao uma meta: assim qualquer aumento
        # reprova na hora. Comecou em 52; cada limpeza que troca um decorativo
        # por cobertura real permite baixar mais um degrau. Nunca sobe.
        _TETO = 48
        add('decorative_checks_never_grow', _decor <= _TETO,
            f"{_decor} checks apenas confirmam que uma funcao existe pelo nome "
            f"(teto: {_TETO}). Um check assim passa mesmo se o corpo virar "
            f"`return None` - prefira chamar a funcao e conferir o resultado.")
    except Exception as _e:
        add('self_test_quality_contract', False, _e)

    # ---------- Revisao profunda: placebo e dano colateral ----------
    try:
        from azor_modules.engine import _all_tasks as _T2
        _tasks2 = list(_T2())
        _auto2 = {t.id for t in _tasks2 if getattr(t, 'automatic', True)}

        # Timer de 0,5 ms: ativo != alcancando o jogo.
        #
        # Desde o Windows 10 2004 o pedido de timer vale so para o processo que
        # pediu. O app mostrava "Timer 0,5 ms ativo" sem checar a chave global -
        # ou seja, anunciava um ganho que morria dentro do proprio otimizador.
        _sc = core.timer_global_scope()
        # Checar o RESULTADO de latency_engine_status(), nao a existencia da
        # funcao: a primeira versao deste check passava mesmo depois de eu
        # arrancar a chamada de dentro do status. Invariante que so procura
        # texto nao guarda comportamento nenhum.
        _st = core.latency_engine_status()
        add('timer_status_knows_if_it_reaches_the_game',
            isinstance(_st.get("global"), dict)
            and set(_st["global"]) >= {"scope", "reaches_the_game"}
            and 'GlobalTimerResolutionRequests' in core_text,
            'timer por processo nao ajuda o jogo, e a tela nao pode dizer que ajuda')
        add('timer_scope_is_shown_to_the_client',
            'timer-scope-warn' in css_text
            and 'reaches_the_game' in app_text,
            'o aviso tem de chegar na tela, nao ficar so no backend')
        add('timer_scope_never_over_claims',
            _sc["scope"] in ("process", "pending", "system")
            and (_sc["reaches_the_game"] is (_sc["scope"] == "system")),
            'so o alcance "system" pode afirmar que o timer chega ao jogo')

        # Tela cheia exclusiva: o ganho e no jogo, o preco era no PC inteiro.
        add('fullscreen_exclusive_is_per_game_not_global',
            'fortnite_fullscreen_exclusive' in _auto2
            and 'fullscreen_exclusive' not in _auto2,
            'a chave global do GameConfigStore derruba overlay de Discord e OBS '
            'no sistema inteiro para ganhar latencia so dentro da partida')
        add('per_game_fullscreen_uses_the_windows_own_mechanism',
            'APPCOMPAT_LAYERS' in core_text and 'DISABLEDXMAXIMIZEDWINDOWEDMODE' in core_text,
            'e a mesma chave da caixinha nas Propriedades do exe: o cliente confere e desfaz por la')
        add('per_game_fullscreen_preserves_existing_flags',
            'def _layers_value_for' in core_text,
            'sobrescrever a chave apagaria outras flags de compatibilidade do exe')
        # Idem: perguntar a lista, nao ao texto. Trocar o exe por None mantinha
        # a palavra APPCOMPAT_LAYERS no corpo e o check passava feliz.
        _fort_exe = (core.detect_fortnite() or {}).get("exe")
        _tracked = {(r, p.casefold(), n.casefold()) for r, p, n in core.tracked_registry()}
        add('per_game_fullscreen_is_in_the_baseline',
            (not _fort_exe) or
            ("HKCU", core.APPCOMPAT_LAYERS.casefold(), str(_fort_exe).casefold()) in _tracked,
            'o nome da chave e o caminho do exe, entao so o baseline dinamico a captura - '
            'sem isso a reversao falha com "sem baseline para:"')
    except Exception as _e:
        add('deep_review_contract', False, _e)

    # ---------- Auditoria tecnica do catalogo ----------
    #
    # Cada check aqui guarda um achado da auditoria. Sao tweaks que ESTAVAM no
    # lote automatico e nao deviam estar, ou valores que a internet copia ha uma
    # decada e que hoje custam o oposto do que prometem.
    try:
        # Os valores sairam do corpo de set_azor_fps_boost_power para
        # power_policy.POWER_SETTINGS; procurar o texto no corpo reprovava um plano
        # certo e aprovaria um errado. Agora a pergunta e ao valor que o app grava.
        from azor_modules.power_policy import POWER_EXPECTED as _pe

        # O tweak mais copiado da internet, e um dos mais contraproducentes.
        add('power_plan_never_pins_cpu_minimum_at_100',
            _pe.get('cpu_min_ac') == 5,
            'CPU cravada no maximo 24/7 queima folga termica; turbo moderno vive '
            'dessa folga, e o preco aparece no 1% low de partida longa')
        add('power_plan_keeps_the_levers_that_actually_ramp',
            _pe.get('epp_ac') == 0 and _pe.get('boost_mode_ac') == 2,
            'quem faz o clock subir em ~1 ms e o Speed Shift via EPP, nao o minimo travado')
        add('cooling_policy_is_active_not_passive',
            _pe.get('cooling_policy_ac') == 1,
            'Passivo (0) manda o Windows DESACELERAR o processador antes de acelerar a '
            'ventoinha - de cabeca para baixo num plano chamado FPS BOOST')

        # Tweaks que cobram estabilidade e nao devolvem frametime.
        _sys = (ROOT / 'azor_modules' / 'system.py').read_text(encoding='utf-8', errors='replace')
        _gpu = (ROOT / 'azor_modules' / 'gpu.py').read_text(encoding='utf-8', errors='replace')
        from azor_modules.engine import _all_tasks as _T
        _auto = {t.id for t in _T() if getattr(t, 'automatic', True)}
        # Os modos Maximo e Agressivo decidem pela politica, nao pelo campo
        # `automatic`: sem somar o que eles aplicam, estas regras passavam com o
        # item dentro do lote.
        from azor_modules import policy as _pol
        _auto |= {t.id for t in _T() for _p in ('maximo', 'agressivo')
                  if t.apply is not None and _pol.automatic_decision(t, {'resolved_profile': _p, 'hardware': {'ok': True}})[0]}
        add('svchost_grouping_is_not_automatic',
            'svchost_split_threshold' not in _auto,
            'juntar os servicos num processo so troca estabilidade por cosmetica: '
            'zero FPS, zero frametime, e a falha de um servico derruba os vizinhos')
        add('tdr_delay_is_not_automatic',
            'tdr_delay' not in _auto,
            'aumentar o TdrDelay nao evita a GPU travar - so troca 2 s de tela '
            'congelada por 10 s, sem nenhum ganho de desempenho junto')
        add('experimental_tweaks_stay_out_of_the_one_click',
            all(i not in _auto for i in ('win32_priority_separation', 'memory_integrity_off',
                                         'processor_idle_disable', 'mpo_off')),
            'o clique unico nao pode aplicar o que depende de teste A/B do cliente')

        # CPU hibrida.
        add('windows_11_detected_by_build_not_by_name',
            'def is_windows_11' in core_text and '22000' in core_text,
            'platform.release() devolve "10" nos dois; quem separa e a build 22000')
        add('hybrid_cpu_is_reported_as_a_structural_finding',
            'Thread Director' in core_text and 'cpu_topology()' in core_text,
            'CPU hibrida no Windows 10 custa 1% low e nenhum registro conserta')
        add('hybrid_cpu_never_gets_old_affinity_hacks',
            'win32_priority_separation' not in _auto,
            'mexer no quantum atrapalha o agendador moderno em CPU hibrida')

        # Portao termico.
        add('ultra_refuses_to_run_on_a_hot_machine',
            '_ultra_hot' in core_text and 'antecipa o throttle' in core_text,
            'manter tudo no maximo num PC a 80 C entrega throttle, nao FPS')
    except Exception as _e:
        add('catalog_audit_contract', False, _e)

    # ---------- Itens da revisao completa ----------
    try:
        # Niveis de log. A assinatura antiga continua valendo, senao as centenas
        # de chamadas existentes teriam de mudar de uma vez - e alguma quebraria.
        add('log_has_levels',
            all(f'"{lvl}"' in core_text or f"'{lvl}'" in core_text
                for lvl in ("SUCCESS", "WARNING", "ERROR", "DEBUG"))
            and 'def log_success' in core_text and 'LOG_LEVELS' in core_text)
        add('log_keeps_the_old_single_argument_call',
            'def log(message: str, level: str = "INFO")' in core_text,
            'centenas de chamadas log("texto") existentes nao podem quebrar')
        add('debug_log_is_hidden_from_normal_users',
            '_dev_mode()' in core_text and 'if lvl == "DEBUG"' in core_text,
            'log cheio de rastreio de excecao assusta quem nao e tecnico')

        # Iniciar com o Windows: existe, confirma por releitura, e NAO liga sozinho.
        _sw = _body_of('set_start_with_windows', core_text)
        add('start_with_windows_actually_works',
            'reg_write' in _sw and 'reg_read' in _sw
            and 'Inicialização automática foi desativada' not in core_text,
            'a build anterior recusava ligar e devolvia sempre False')
        add('start_with_windows_verifies_by_reading_back',
            'back.get("value")' in _sw,
            'gravou != aplicou; quem confirma e a releitura')
        add('start_with_windows_is_off_by_default',
            '"start_with_windows": False' in core_text,
            'o usuario pediu para nunca ligar inicializacao automatica sem consentimento')
        add('start_with_windows_reads_the_registry_not_a_json',
            'def get_start_with_windows' in core_text
            and 'reg_read' in _body_of('get_start_with_windows', core_text),
            'confiar num JSON e como o app perdia o estado real do Windows')

        # Relatorio no lugar e com o nome pedidos.
        add('report_goes_to_documents_azor_reports',
            '"AZOR Optimization"/"Reports"' in core_text)
        add('report_filename_carries_date_and_time',
            'AZOR_Report_{stamp}' in core_text and '%Y-%m-%d_%H-%M-%S' in core_text,
            'sem data e hora o relatorio de hoje apaga o de ontem')

        # P-cores / E-cores.
        _topo = core.cpu_topology()
        add('cpu_topology_uses_the_official_api',
            'GetLogicalProcessorInformationEx' in core_text
            and 'EfficiencyClass' in core_text or 'eff' in _body_of('cpu_topology', core_text),
            'uma tabela de modelos envelhece a cada lancamento; a API nao')
        add('cpu_topology_says_it_does_not_know',
            _topo.get("hybrid") is not None or 'não identificada' in str(_topo.get("detail")),
            'processador nao hibrido nao pode receber uma divisao P/E inventada')
        add('hybrid_split_only_when_really_hybrid',
            (_topo.get("performance_cores") is None) == (not _topo.get("hybrid")),
            'P e E so aparecem quando o Windows separou de verdade')
    except Exception as _e:
        add('full_review_contract', False, _e)

    # ---------- Falhas que o cliente via na tela ----------
    try:
        _w = _body_of('_safe_json_write', core_text)
        add('json_write_uses_a_unique_temp_name',
            'os.getpid()' in _w and 'get_ident()' in _w,
            'com nome fixo, duas threads do servidor e o processo do Guardian '
            'disputam o mesmo .tmp e o /api/summary cai com WinError 32')
        add('json_write_retries_the_replace',
            'for attempt in range(' in _w and 'time.sleep' in _w,
            'no Windows o replace precisa de DELETE no destino, e quem esta lendo segura isso')
        add('json_write_cleans_its_temp',
            'finally' in _w and 'unlink' in _w,
            'gravacao que morre no meio nao pode deixar lixo acumulando em data/')
        add('cache_write_never_breaks_a_request',
            'def _cache_json_write' in core_text
            and '_cache_json_write(HARDWARE_PROFILE_FILE' in core_text,
            'um cache derivado derrubou a tela inicial inteira ao nao conseguir gravar')

        _gap = core.admin_blocked_tweaks()
        add('admin_gap_is_counted_from_the_catalog',
            isinstance(_gap.get("total"), int) and _gap["total"] > 0
            and 'admin_blocked_tweaks' in core_text
            and '/api/admin-gap' in source,
            'o numero de ajustes bloqueados nao pode ser escrito a mao: o catalogo cresce')
        # Verificar ORDEM, nao distancia em caracteres: a primeira versao deste
        # check exigia a chamada nos primeiros 1200 chars da renderHome e
        # reprovava por causa do tamanho do HTML do heroi. O que importa e que o
        # aviso de permissao venha antes dos outros banners da tela inicial.
        add('admin_gap_is_visible_where_the_client_clicks',
            'function adminGapBanner' in app_text and 'admin-gap-banner' in css_text
            and '${adminGapBanner()}' in app_text
            and app_text.index('${adminGapBanner()}') < app_text.index('${startupRestoreBanner()}'),
            'o aviso vivia so no Arsenal; o cliente clica BOOST na tela inicial')
        add('boost_admits_what_it_could_not_apply',
            "'/api/admin-gap'" in app_text and 'BLOQUEADO' in app_text,
            'terminar anunciando "39 aplicadas" com 27 puladas em silencio e mentir por omissao')
    except Exception as _e:
        add('client_visible_failures_contract', False, _e)

    # ---------- O que o AZOR custa enquanto o cliente joga ----------
    #
    # A queixa foi "senti mais delay depois de instalar". Era verdade, e cada
    # check aqui guarda uma das causas medidas, para que nenhuma volte.
    try:
        monitor_text = (ROOT / 'azor_input_monitor.py').read_text(encoding='utf-8', errors='replace')
        agent_text = (ROOT / 'azor_agent.py').read_text(encoding='utf-8', errors='replace')

        _hot = _body_of('_process_names', core_text) + _body_of('_pids_for', core_text)
        add('hot_path_never_spawns_tasklist',
            'def _process_list' in core_text and '_tasklist_rows' not in _hot
            and '_process_list()' in _hot,
            'tasklist.exe custa 100,5 ms medidos; o caminho quente roda dentro da partida')
        add('game_detection_uses_foreground_window',
            'GetForegroundWindow' in core_text and 'def game_focused' in core_text,
            'saber se o jogo esta na frente tem de custar microssegundos, nao uma varredura')
        add('game_focus_is_cached',
            '_GAME_FOCUS_CACHE' in core_text,
            'sem cache, game_focused() relia settings do disco ate 125x/s no laco do stream')

        # Procurar no corpo do HANDLER, nao no arquivo inteiro: a propria linha
        # deste check carregava a string do giro antigo, e um teste que se
        # enxerga no espelho reprova a correcao que ele veio proteger.
        _stream = _body_of('_stream_input_live', source)
        add('input_stream_waits_instead_of_spinning',
            'wait_for_change' in _stream and 'sleep(0.002)' not in _stream,
            'o laco acordava 500x/s mesmo com o cliente dentro do jogo')
        add('input_monitor_can_wake_its_reader',
            'def _bump' in monitor_text and '_changed' in monitor_text,
            'o contador de revisao precisa acordar quem espera, senao volta o giro')

        add('raw_input_sink_released_during_play',
            'game_focused()' in source and 'input_monitor.stop()' in source
            and 'modo silencio' in source,
            'RIDEV_INPUTSINK entrega mil relatorios por segundo ao AZOR enquanto o cliente mira')
        add('gpu_sampler_stops_during_play',
            'def monitor_snapshot' in core_text
            and 'game_focused().get("focused")' in core_text.split('def monitor_snapshot')[1][:900],
            'um nvidia-smi de longa duracao nao pode sobreviver a partida')
        add('guardian_slows_down_during_play',
            'time.sleep(20 if game else 15)' in agent_text,
            'a cadencia estava invertida: acordava MAIS justamente dentro do jogo')

        _fp = core.background_footprint()
        add('footprint_is_reported_to_the_client',
            isinstance(_fp.get("suspended"), list) and len(_fp["suspended"]) >= 4
            and 'footprint' in app_text,
            'o cliente que reclamou precisa ver o app saindo da frente')
    except Exception as _e:
        add('background_cost_contract', False, _e)

    # ---------- Area de perifericos ----------
    #
    # A regra desta tela e uma so: nenhum numero aparece sem leitura real. O que
    # existia antes mostrava "1600 DPI / 1000 Hz" tirados do PERFIL, ou seja, do
    # que o proprio usuario escolheu - apresentado como se fosse leitura do
    # dispositivo. DPI o Windows nao expoe por API nenhuma; polling o AZOR mede.
    try:
        _caps = core.input_capabilities()
        add('peripherals_never_claim_readable_dpi',
            all(not v["readable"]["dpi"] for v in _caps.values())
            and 'DPI_UNAVAILABLE_REASON' in core_text,
            'DPI vive no firmware do mouse; qualquer numero na tela ou veio do usuario ou foi inventado')
        add('peripherals_polling_is_measured_not_guessed',
            'def _polling_estimate' in (ROOT / 'azor_input_monitor.py').read_text(encoding='utf-8', errors='replace')
            # Procura a DEFINICAO, nao a palavra: o comentario que explica por que
            # a heuristica saiu cita o nome dela, e um check por texto solto
            # reprovava justamente a documentacao da propria correcao.
            and 'def _supported_hz' not in core_text,
            'a heuristica antiga adivinhava a taxa maxima pelo NOME do dispositivo')
        add('peripherals_ui_shows_unavailable_instead_of_a_number',
            'nao disponivel' in app_text.replace('ã', 'a').replace('í', 'i').replace('ú', 'u')
            or 'não disponível' in app_text)

        # Remapeamento: existe, salva, e NAO mente sobre ter aplicado.
        _remap = core.controller_remap()
        add('remap_never_reports_applied_without_a_driver',
            _remap.get("applied") is False and _remap.get("driver_ready") is False,
            'sem ViGEm + HidHide o jogo enxerga os dois controles e conta entrada dobrada')
        add('remap_documents_its_integration_point',
            'ViGEmBus' in core_text and 'HidHide' in core_text and 'PONTO DE INTEGRACAO' in core_text,
            'quem for implementar precisa achar onde, sem caçar no codigo')
        add('remap_ui_states_it_is_not_applied',
            'Salvo como perfil, não aplicado ao controle' in app_text)
        _saved = core.save_controller_remap({"A": "B", "B": "B", "ZZ": "A"})
        add('remap_rejects_invalid_pairs',
            _saved["mapping"] == {"A": "B"},
            'botao inexistente e troca de um botao por ele mesmo nao entram')
        core.save_controller_remap({})

        # Aparencia Xbox/PS5 e so desenho.
        add('pad_skin_is_visual_only',
            'padSkin' in app_text and 'Nao toca em driver nem no dispositivo' in app_text,
            'trocar a aparencia nao pode mexer em como o Windows identifica o controle')
        add('peripherals_carry_no_third_party_logo',
            not any(b in app_text.lower() for b in ('logitech', 'razer', 'corsair', 'hyperx', 'steelseries')),
            'o AZOR nao reproduz marca de terceiro no proprio produto')

        # O texto de venda dos perfis anunciava "1600 DPI, 1000 Hz" ao lado do
        # card que admite nao saber o DPI. O numero era o alvo escolhido no
        # perfil, nao leitura do aparelho - e nenhum cliente le assim.
        _desc = re.findall(r"desc:'([^']*)'", app_text)
        _mentirosos = [d for d in _desc
                       if re.search(r"\d+\s*(DPI|Hz)", d, re.I)]
        add('preset_copy_advertises_no_device_number',
            not _mentirosos, _mentirosos or 'nenhuma descricao promete DPI/Hz')
        add('preset_grid_says_where_azor_stops',
            'preset-truth' in app_text and 'firmware do aparelho' in app_text,
            'o cliente precisa saber o que entrou no Windows e o que ficou so como perfil')

        # Performance: o rAF do gamepad rodava sempre, em qualquer tela.
        add('gamepad_loop_only_runs_on_the_peripherals_page',
            "if(!isInputVisible() || !$('.controller-svg')){stopGamepadVisual();return}" in app_text
            and "document.hasFocus()" in app_text
            and "window.addEventListener('blur',pauseInputVisuals)" in app_text,
            'antes era um requestAnimationFrame eterno a 60 fps, mesmo atras do jogo')
    except Exception as _e:
        add('peripherals_contract', False, _e)

    # ---------- Plano de acao ----------
    #
    # 70 tweaks, um indice, um relatorio de gargalo e uma prova medida - e nenhuma
    # resposta para a unica pergunta que o cliente faz: "o que eu faco primeiro?".
    # Uma lista de 70 itens nao e um plano; e um catalogo.
    try:
        _plan = core.action_plan("competitive")
        add('action_plan_exists', _plan.get("ok") is True and '/api/action-plan' in source)
        add('plan_puts_hardware_limits_first',
            not _plan["steps"] or _plan["steps"][0]["weight"] >= 900
            or not [s for s in _plan["steps"] if s["kind"] == "estrutural"],
            'monitor a 60 Hz num painel de 144 devolve mais que os 70 ajustes somados')
        add('plan_is_ordered_by_weight',
            all(_plan["steps"][i]["weight"] >= _plan["steps"][i + 1]["weight"]
                for i in range(len(_plan["steps"]) - 1)))
        _no_why = [s["title"] for s in _plan["steps"] if not (s.get("why") or "").strip()]
        add('every_plan_step_says_why_it_is_there', not _no_why, _no_why)
        add('plan_ranks_by_declared_metric_not_opinion',
            'METRIC_WEIGHT' in core_text and '_metric_rank' in core_text,
            'a posicao sai da metrica que o proprio tweak declara mover')
        add('plan_promises_order_not_numbers',
            'nao por ganho prometido' in (_plan.get("note") or "").replace('ã', 'a').replace('ç', 'c'))
        add('manual_steps_rank_below_automatic',
            'weight - 200' in core_text.replace('(weight - 200)', 'weight - 200'),
            'risco alto nao e recomendacao, e escolha informada')
    except Exception as _e:
        add('action_plan_contract', False, _e)

    add('arsenal_is_searchable',
        'arsenalQuery' in app_text and 'arsenalSearch' in app_text,
        'com 70 linhas, rolar procurando "Nagle" deixou de ser aceitavel')

    # ---------- FPS: monitor e prioridade ----------
    #
    # As duas maiores alavancas que o app so sabia DIAGNOSTICAR. Detectar e nao
    # consertar e a pior combinacao possivel: o cliente le que tem problema e
    # continua com ele.
    try:
        add('refresh_rate_is_fixable_not_just_reported',
            'def set_display_refresh_verified' in core_text
            and any(t.id == 'display_max_refresh' for t in _all),
            'o relatorio de gargalo detectava 60 Hz num monitor de 144 e so mandava ir nas Configuracoes')
        add('refresh_change_is_tested_before_applied',
            'CDS_TEST' in core_text,
            'pedir um modo que o monitor recusa deixaria a tela preta ate o Windows reverter sozinho')
        add('refresh_rate_reads_the_modes_the_monitor_offers',
            'def available_refresh_rates' in core_text)

        _prio = next((t for t in _all if t.id == 'game_priority_engine'), None)
        add('game_priority_engine_exists', _prio is not None)
        # Checagem estrutural: a constante de tempo real nao pode existir no core.
        # A primeira versao procurava a palavra "REALTIME" e reprovava por causa de
        # RealTimeProtectionEnabled, do probe do Defender - falso positivo classico
        # de check por texto solto.
        add('game_priority_never_uses_realtime',
            'REALTIME_PRIORITY_CLASS' not in core_text
            and 'HIGH_PRIORITY_CLASS = 0x00000080' in core_text,
            'em tempo real o jogo passa na frente do driver de entrada e do audio, e o PC engasga')
        add('game_priority_does_not_demote_unknown_processes',
            'Nao rebaixa nada de segundo plano' in core_text or 'nao rebaixa' in core_text.lower(),
            'derrubar processo que o app nao conhece quebra navegador e captura')
        add('game_priority_is_a_session_engine',
            _prio is not None and 'session' in (_prio.tags or ()),
            'prioridade morre com o processo; nao escreve nada e por isso nao entra no baseline')
        add('session_engines_restart_with_the_app',
            'GAME_PRIORITY.start()' in core_text and 'restore_session_engines' in core_text)

        add('driver_settings_are_guided_not_written',
            'def driver_guide' in core_text and 'DRIVER_GUIDES' in core_text
            and 'nvlddmkm' not in core_text,
            'escrever no registro do driver quebra na proxima atualizacao e some sem avisar')
        add('driver_guide_matches_the_installed_gpu',
            isinstance(core.driver_guide().get('vendor'), str))
    except Exception as _e:
        add('fps_contract', False, _e)

    # ---------- Instancia unica e saida limpa ----------
    #
    # O bug: o launcher encerrava o backend antigo com Stop-Process -Force, que e
    # TerminateProcess. O processo morria sem remover o proprio icone da bandeja,
    # e o Windows acumulava um "AZOR" fantasma por abertura. Nao eram varios apps
    # rodando - era um app e varios fantasmas.
    add('old_instance_is_asked_before_being_killed',
        '--quit-running' in launcher and launcher.index('--quit-running') < launcher.index('Stop-Process'),
        'o pedido educado precisa vir ANTES do encerramento forcado, senao o icone vira fantasma')
    add('backend_can_quit_cleanly_on_request',
        'QUIT_EVENT_NAME' in source and 'def watch_quit_event' in source
        and 'def quit_running_instance' in source)
    add('clean_quit_removes_the_tray_icon',
        'tray.stop()' in source and 'Shell_NotifyIconW(NIM_DELETE' in _tray_text,
        'e a unica coisa que separa "fechou" de "virou fantasma na bandeja"')
    add('quit_waits_for_the_old_pid_to_die',
        '_pid_alive' in source,
        'sinalizar e sair na hora deixaria dois backends na mesma porta')
    # O vigia foi amarrado ao tray na primeira versao, e um backend --no-browser
    # ficava surdo ao pedido de saida: dois processos na mesma porta, o antigo
    # respondendo. Apareceu como catalogo com 68 itens na tela e 70 no disco.
    _main = source[source.rfind('def main():'):]
    add('quit_watcher_does_not_depend_on_the_tray',
        'watch_quit_event' in _main
        and _main.index('watch_quit_event') > _main.index('tray = None'),
        'saida limpa e sobre o processo, nao sobre o icone')
    add('quit_reports_failure_when_it_did_nothing',
        'Quit requested but no listener' in source,
        'dizer "ok" sem ter feito nada fazia o launcher achar que a porta estava livre')

    # ---------- BOOST total ----------
    add('boost_applies_every_page',
        'def full_optimize' in core_text and '"full_optimize"' in source
        and 'apply_input_profile' in core_text.split('def full_optimize')[1][:4000],
        'o cliente apertava BOOST, via "concluido" e achava que Input Lab e Fortnite ja tinham sido feitos')
    add('boost_profile_is_chosen_on_the_button',
        'boost-profiles' in app_text and 'boost-profile ' in app_text)
    add('boost_covers_input_gpu_and_fortnite',
        all(x in core_text for x in ('Input Lab - ', 'GPU por jogo', 'Fortnite - qualidade competitiva')))
    add('graphic_preset_stays_out_of_non_competitive_profiles',
        'preset gr' in core_text and 'so entra no COMPETITIVO' in core_text.replace('só', 'so'),
        'forcar preset grafico em quem joga campanha estraga a experiencia que a pessoa escolheu')
    add('boost_refuses_to_edit_fortnite_while_it_runs',
        'sobrescrever na sa' in core_text,
        'editar o ini com o jogo aberto faz o proprio jogo desfazer na saida')

    # ---------- Segundo plano ----------
    add('background_start_is_a_setting',
        'def should_start_minimized' in core_text and '"start_minimized"' in source,
        'iniciar em segundo plano tem de ser escolha, nao imposicao')
    add('first_launch_always_appears',
        'def first_launch_done' in core_text and 'first_launch_at' in core_text,
        'um cliente que da dois cliques e nao ve nada abrir liga para o suporte')
    add('minimized_start_waits_for_the_window',
        'def hide_ui_window' in source and 'deadline' in source,
        'o Edge demora um tempo variavel para criar a janela; esconder cedo demais falhava as vezes')
    add('minimized_start_tells_the_user_where_it_went',
        'tray.notify(' in source,
        'sumir sem avisar e indistinguivel de nao ter aberto')

    # ---------- Alvos por componente ----------
    #
    # Estes existem porque a versao anterior tinha o mesmo defeito duas vezes: um
    # ajuste que pede administrador ANTES de olhar responde "exige administrador"
    # num PC onde ele nem se aplicaria.
    try:
        _mem = (ROOT / 'azor_modules' / 'memory.py').read_text(encoding='utf-8', errors='replace')
        _pow = (ROOT / 'azor_modules' / 'power.py').read_text(encoding='utf-8', errors='replace')
        add('component_tweaks_diagnose_before_asking_permission',
            _mem.index('ram = float(') < _mem.index('if not core.is_admin():')
            and _pow.index('battery') < _pow.index('if not core.is_admin():'),
            'RAM insuficiente e notebook sao respostas melhores que "exige administrador"')
    except Exception as _e:
        add('component_tweaks_diagnose_before_asking_permission', False, _e)
    add('hidden_power_option_is_revealed_then_restored',
        'def unhide_processor_idle_attribute' in core_text and 'def hide_processor_idle_attribute' in core_text,
        'IDLEDISABLE vem oculto; sem revelar, o tweak seria codigo morto na maioria das maquinas')
    add('idle_read_has_no_side_effect',
        'allow_unhide: bool = False' in core_text,
        'a leitura da tela nao pode alterar as opcoes de energia do usuario')
    add('device_paths_are_discovered_not_hardcoded',
        'def pci_instances' in core_text and 'def usb_hub_instances' in core_text,
        'caminho de instancia PCI/USB so existe naquela maquina')
    try:
        _ram_gated = [t for t in _all if t.id in ('kernel_no_paging', 'memory_compression_off')]
        add('ram_hungry_tweaks_are_gated_by_ram', len(_ram_gated) == 2
            and all(t.compatible is not None for t in _ram_gated),
            'prender memoria em PC com pouca RAM tira espaco de quem precisa mais: o jogo')
        _boot_critical = [t.id for t in _all if t.id in ('storage_msi', 'gpu_msi', 'memory_integrity_off')
                          and (t.automatic or not t.restart)]
        add('boot_critical_tweaks_are_manual_and_reboot_aware', not _boot_critical, _boot_critical)
    except Exception as _e:
        add('component_tweak_contract', False, _e)

    # ---------- Modulo Reparo ----------
    #
    # Reparo e a unica familia do catalogo que MELHORA o PC desfazendo coisa. Ela
    # tem duas armadilhas proprias: prometer desfazer o conserto (o app nao
    # desliga firewall de cliente) e gritar num PC saudavel (o que treina o
    # cliente a ignorar o aviso justamente quando ele importa).
    try:
        from azor_modules import repair as _repair
        _reps = _repair.tasks()
        _promises_undo = [t.id for t in _reps if t.reversible or t.revert is not None]
        add('repair_never_promises_to_undo_a_repair', not _promises_undo, _promises_undo)
        _no_reason = [t.id for t in _reps if 'reversível pelo AZOR' not in (t.trade_off or '')
                      and 'reversivel pelo AZOR' not in (t.trade_off or '')]
        add('repair_explains_why_it_does_not_undo', not _no_reason, _no_reason)
        add('repair_runs_before_the_rest',
            _eng.MODULES[0] is _repair,
            'nao adianta otimizar em cima de um Windows que outro programa quebrou')
        _repair_text = (ROOT / 'azor_modules' / 'repair.py').read_text(encoding='utf-8', errors='replace')
        add('repair_diagnoses_before_asking_for_permission',
            '_needs_admin_to_fix' in _repair_text and _repair_text.count('if not core.is_admin():') == 1,
            'num PC saudavel a resposta certa e "nada a reparar", nao "exige administrador"')
        add('repair_block_is_quiet_when_nothing_is_broken',
            'repair-block card clean' in app_text and 'Nada quebrado por outro programa' in app_text)
        add('bcd_override_detected_by_name_not_value',
            'BCD_TIMER_OVERRIDES' in core_text and 'rf"(?mi)^{name}' in core_text,
            'o valor sai traduzido num Windows em portugues; o nome da opcao nao')
        add('essential_services_exclude_user_preference',
            'WSearch' not in str(core.ESSENTIAL_SERVICES) and 'WinDefend' not in str(core.ESSENTIAL_SERVICES),
            'busca desligada e preferencia; Defender desligado e normal com antivirus de terceiro')
    except Exception as _e:
        add('repair_module_contract', False, _e)

    add('fsutil_is_read_in_any_language',
        '_fsutil_scalar' in core_text and 'r"=\\s*(\\d)"' not in core_text,
        'o fsutil em portugues imprime "e: 2" e nao "= 2"; procurar por "=" nao achava nada')
    add('arsenal_visits_each_tweak_once',
        'def arsenal(' in engine_text and 'analyze_optimizations(str(profile' not in core_text,
        'build_plan + analyze rodavam o compatible de todos os tweaks duas vezes')
    add('relaunch_uses_the_official_launcher',
        'def relaunch_as_admin' in core_text and 'AZOR Optimization.bat' in core_text
        and '-Verb' in core_text and '"relaunch_admin"' in source,
        'pedir ao cliente para fechar e reabrir a mao e onde a maioria desiste')
    add('relaunch_reports_a_refused_uac_as_refusal',
        'RECUSADO' in core_text and '"refused": True' in core_text,
        'UAC negado e uma escolha do usuario, nao uma falha do app')

    # ---------- Indice AZOR e medicao fina ----------
    #
    # O numero grande da tela e o ponto onde um app do genero costuma mentir.
    # Estes checks existem para que ele nao consiga: cada componente mostra a
    # leitura que o produziu, e o que nao pode ser medido sai da conta em vez de
    # virar zero (que baixaria a nota) ou o maximo (que inflaria).
    try:
        _idx = core.azor_index()
        add('azor_index_is_traceable', all((p.get('evidence') or '').strip() for p in _idx['parts']),
            'todo componente mostra a leitura que gerou os pontos')
        add('azor_index_excludes_what_it_cannot_measure',
            'unmeasured' in _idx and _idx['possible'] == sum(p['max'] for p in _idx['parts'] if p['measured']),
            'componente sem sensor nao pode virar zero silencioso')
        add('azor_index_never_exceeds_its_scale', 0 <= _idx['score'] <= _idx['possible'] <= 1000,
            f"{_idx['score']}/{_idx['possible']}")
        add('azor_index_says_it_is_not_fps', 'nao de FPS' in (_idx.get('note') or ''),
            'a nota do indice tem de negar a leitura de "isso e meu ganho de FPS"')
        _foot = core.optimization_footprint()
        add('footprint_is_counted_from_the_catalog',
            _foot['tweaks'] == len(_all) and _foot['registry_values'] >= 20,
            _foot)
    except Exception as _e:
        add('azor_index_contract', False, _e)

    add('measurement_reports_the_tail_not_just_the_mean',
        all(k in core_text for k in ('p99_us', 'stalls', 'p99_overshoot_us')),
        'a media esconde exatamente o que o jogador sente como travadinha')
    add('tcp_is_read_by_cmdlet_not_by_translated_text',
        'Get-NetTCPSetting' in core_text and '_TCP_ALIASES' in core_text,
        'num Windows em portugues a linha do netsh tem outro nome e a busca por rotulo falhava')
    add('nic_power_falls_back_to_pnp_capabilities',
        'PnPCapabilities' in core_text and 'nic_driver_key' in core_text,
        'varios drivers nao publicam a classe de energia; o interruptor real e a chave do dispositivo')
    add('azor_windows_bridge_resolves_its_cli',
        'cli = _contract_path("CLI", AZOR_WINDOWS_CLI)' in core_text and 'cli_path' not in core_text,
        'a ponte referenciava uma variavel que nao existia e falhava sempre')

    # ---------- Modulo 3: persistencia do plano de energia ----------
    guard_path = ROOT/'azor_power_guard.py'
    guard_text = guard_path.read_text(encoding='utf-8', errors='replace') if guard_path.exists() else ''
    add('power_guard_module', guard_path.is_file() and guard_path.stat().st_size > 0)
    add('power_guard_diagnoses_before_acting', 'def diagnose' in guard_text and 'causes' in guard_text,
        'dizer qual das 5 causas e a deste PC vale mais que aplicar as 5 camadas as cegas')
    add('power_guard_detects_modern_standby', 's0 low power idle' in guard_text.lower() and 'overlay' in guard_text,
        'em Modern Standby quem manda e o overlay, nao o esquema')
    add('power_guard_detects_oem_software', 'OEM_SIGNATURES' in guard_text and 'lenovovantage' in guard_text.lower())
    add('power_guard_never_uninstalls_oem', 'nunca desinstala nem desativa nada disso' in guard_text,
        'desligar o servico do fabricante costuma levar junto a curva de ventoinha')
    add('power_guard_task_runs_only_powercfg', 'powercfg.exe' in guard_text and 'AzorPowerGuard' in guard_text,
        'a unica persistencia que o AZOR deixa nao pode executar codigo do AZOR')
    add('power_guard_task_is_opt_in', 'NUNCA e criada automaticamente' in guard_text)
    add('power_guard_overlay_never_guesses', 'nao e adivinhado' in guard_text and 'OVERLAY_GUIDS' in guard_text)
    add('power_guard_watchdog_dies_with_app', 'Isto NAO e um servico' in guard_text and 'daemon=True' in guard_text)
    add('power_guard_persistence_test', 'def persistence_test_arm' in guard_text and 'def persistence_test_check' in guard_text and 'reboots_survived' in guard_text,
        'fechar o ciclo com o reboot e o que prova que a correcao funcionou')
    add('power_guard_api', '/api/power-guard' in source and '"power_policy_lock_on"' in source and '"power_guard_task_on"' in source)
    try:
        _layers = power_guard.layers_state()
        add('power_guard_six_layers', [l['id'] for l in _layers] == ['A','B','C','D','E','F'], [l['id'] for l in _layers])
        add('power_guard_layers_declare_cost', all((l.get('cost') or '').strip() for l in _layers),
            'uma camada sem custo declarado e uma camada vendida pela metade')
    except Exception as _e:
        add('power_guard_six_layers', False, _e)

    # ---------- Hardware Command Center ----------
    for fn in ('storage_health','trim_state','driver_inventory','startup_items','set_startup_item_enabled','hardware_command_center','thermal_snapshot','gpu_throttle_reasons'):
        add('hardware_center_fn:'+fn, callable(getattr(core, fn, None)))
    add('driver_age_scoped_to_vendor', '_is_vendor_driver' in core_text and 'VIRTUAL_DEVICE_PATTERNS' in core_text, 'WAN Miniport must not be reported as an outdated driver')
    add('startup_toggle_is_reversible', 'STARTUP_APPROVED' in core_text and 'Task Manager' in core_text)
    add('startup_never_bulk_disables', 'nunca desativa itens de inicializacao em massa' in core_text)

    # ---------- BIOS Copilot ----------
    add('bios_copilot_present', callable(getattr(core,'bios_copilot',None)) and callable(getattr(core,'set_bios_checklist',None)))
    add('bios_vendor_specific_paths', all(v in core_text for v in ('asrock','gigabyte','"msi"','"asus"')) and 'Ai Overclock Tuner' in core_text)
    add('bios_never_writes_firmware', 'nao escreve firmware' in core_text.lower() or 'não escreve firmware' in core_text.lower())
    add('bios_checklist_verifies_after_reboot', 'verified_after_mark' in core_text and 'reading_when_marked' in core_text)

    # ---------- Live input monitor ----------
    monitor_path = ROOT/'azor_input_monitor.py'
    add('input_monitor_module', monitor_path.is_file() and monitor_path.stat().st_size > 0)
    monitor_text = monitor_path.read_text(encoding='utf-8', errors='replace') if monitor_path.exists() else ''
    add('input_monitor_uses_raw_input', 'RegisterRawInputDevices' in monitor_text and 'RIDEV_INPUTSINK' in monitor_text)
    add('input_monitor_measures_polling', '_polling_estimate' in monitor_text and 'nominal_hz' in monitor_text)
    # Privacy is a product promise, so it is enforced here rather than trusted.
    # Structural, not textual: the snapshot the UI receives must expose only the
    # keys held right now and a counter. Anything shaped like a sequence of typed
    # keys would show up here.
    try:
        import azor_input_monitor as _im
        _snap = _im.MONITOR.snapshot()
        _kb = _snap.get('keyboard') or {}
        add('input_monitor_exposes_no_key_history', set(_kb.keys()) == {'down', 'press_count'}, sorted(_kb.keys()))
        add('input_monitor_down_is_current_state', isinstance(_kb.get('down'), list) and isinstance(_kb.get('press_count'), int))
        _state = vars(_im.MONITOR)
        _identity_attrs = [k for k, v in _state.items()
                           if k not in ('_keys_down',) and isinstance(v, (list, tuple, set, dict))
                           and any(isinstance(x, str) and len(x) <= 3 for x in (v if not isinstance(v, dict) else v.keys()))]
        add('input_monitor_single_key_identity_slot', _identity_attrs == [] or _identity_attrs == ['_buttons_down'],
            f'attributes holding key-like identities: {_identity_attrs}')
    except Exception as _e:
        add('input_monitor_exposes_no_key_history', False, _e)
    add('input_monitor_no_disk_writes', not any(w in monitor_text for w in ('open(', 'write_text', 'Path(')), 'the monitor must never persist anything')
    add('input_monitor_has_watchdog', 'HEARTBEAT_TIMEOUT' in monitor_text and '_last_heartbeat' in monitor_text)
    # GetMessageW blocks forever on an idle machine, so without a periodic timer
    # the heartbeat check never runs and the listener outlives the page.
    add('input_monitor_watchdog_wakes_when_idle', 'WM_TIMER' in monitor_text and 'SetTimer' in monitor_text and 'KillTimer' in monitor_text,
        'the privacy promise has to hold when nobody is touching the PC')
    # A stop/start cycle used to free a window procedure Windows still pointed at,
    # which killed the whole process with an access violation and no traceback.
    add('input_monitor_callbacks_never_freed', '_LIVE_CALLBACKS' in monitor_text and '_LIVE_CALLBACKS.append' in monitor_text)
    add('input_monitor_serialises_restart', '_start_lock' in monitor_text and 'previous.join' in monitor_text)
    add('input_monitor_owns_its_window', 'if self._hwnd == hwnd:' in monitor_text, 'a finishing thread must not clear a newer window handle')
    try:
        import azor_input_monitor as _im2
        _cycles_ok = True
        for _ in range(3):
            if not _im2.start().get('ok'):
                _cycles_ok = False; break
            _im2.stop()
        add('input_monitor_survives_restart_cycles', _cycles_ok)
    except Exception as _e:
        add('input_monitor_survives_restart_cycles', False, _e)
    # A missed key-up used to leave a key lit forever on the Input Lab drawing.
    # The guard asks Windows whether the key is really still down, so this test
    # plants a key that nothing is pressing and expects it to disappear.
    try:
        _mon = input_monitor.MONITOR
        with _mon._lock:
            _mon._keys_down['K'] = time.time() - 5.0
            _mon._keys_vk['K'] = 0x4B
        _still_stuck = 'K' in (_mon.snapshot().get('keyboard') or {}).get('down', [])
        with _mon._lock:
            _mon._keys_down.pop('K', None)
            _mon._keys_vk.pop('K', None)
        add('input_monitor_drops_stuck_keys', not _still_stuck,
            'a key with no physical press must not stay lit')
    except Exception as _e:
        add('input_monitor_drops_stuck_keys', False, _e)
    add('input_stream_pushes_on_change',
        'input_monitor.revision()' in source and 'HEARTBEAT' in source,
        'the stream must not re-send an identical frame 60x/s')
    add('input_live_endpoints', '/api/input-live' in source and '_stream_input_live' in source)
    add('input_stream_closes_connection', 'self.close_connection = True' in source, 'prevents ConnectionAbortedError after a stream ends')
    add('input_monitor_stops_with_server', 'input_monitor.stop()' in source)
    add('input_live_privacy_copy', 'nao grava o que voce digita' in monitor_text or 'não grava' in monitor_text)

    # ---------- New API surface ----------
    for route in ('/api/hardware-center','/api/storage-health','/api/drivers','/api/startup','/api/bios-copilot','/api/thermal','/api/azor-windows','/api/bios-checklist'):
        add('route:'+route, f'path == "{route}"' in source)

    # ---------- UI ----------
    add('ui_helpers_defined',
        "['aux:actionRow'" in app_text and "['aux:statusCard'" in app_text,
        'Windows/Guardian/Maintenance pages called these before they existed')
    add('ui_route_hardware', 'hardware:renderHardware' in app_text and 'function renderHardware' in app_text)
    add('ui_bios_copilot', 'function renderBios' in app_text and 'BIOS Copiloto' in app_text and 'data-bios-check' in app_text)
    add('ui_campaign_profile_button', "data-qprofile=\"campanha\"" in app_text and "campanha" in app_text)
    add('ui_live_input_stream', 'EventSource' in app_text and 'function applyLiveInput' in app_text and 'function pollingPanel' in app_text)
    add('ui_frametime_visuals', 'function frametimeHistogram' in app_text and 'function frametimeTimeline' in app_text)
    add('ui_progressive_hardware_load', 'const section=async' in app_text, 'sections must paint as they arrive')

    # ---------- Identity ----------
    add('accent_is_neon_pink', '--accent:#ff2fc8' in css_text.replace(' ', '') and 'ff2fc8' in app_text.lower())
    add('accent_default_matches_css', '"accent": "#FF2FC8"' in core_text)
    add('display_font_for_numbers', '--font-display' in css_text and 'Bahnschrift' in css_text, 'no webfont request from a local app')
    add('reduced_motion_respected', 'prefers-reduced-motion' in css_text and 'reduce-motion' in css_text)
    add('small_screen_breakpoint', 'max-width:640px' in css_text.replace(' ', ''))
    add('skeleton_loaders', '.skeleton' in css_text and 'function hwSkeleton' in app_text)

    # ---------- Client report ----------
    add('report_is_designed', '_report_html' in core_text and '_report_css' in core_text)
    add('report_not_raw_json_dump', 'Relatório do seu PC' in core_text and 'masthead' in core_text)
    add('report_states_no_system_change', 'nao altera nenhuma configuracao' in core_text or 'não altera nenhuma configuração' in core_text)

    # ---------- Frametime ----------
    diag_text = (ROOT/'azor_game_diag.py').read_text(encoding='utf-8', errors='replace')
    add('frametime_distribution_kept', '_frametime_histogram' in diag_text and '_frametime_timeline' in diag_text)
    add('frametime_timeline_keeps_spikes', 'max(intervals[start:end])' in diag_text, 'averaging would erase the stutters')

    result={'ok':all(x['ok'] for x in checks),'checks':checks,'python':sys.version,'root':str(ROOT)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

def find_edge():
    candidates = [
        shutil.which("msedge"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def hide_ui_window(tray, timeout: float = 14.0) -> bool:
    """Recolhe a janela recem-aberta para a bandeja.

    O Edge leva um tempo variavel para criar a janela; sem esta espera, esconder
    "logo depois de abrir" ora funcionava ora nao, dependendo da carga do PC.
    """
    try:
        from azor_tray import find_ui_window
        import ctypes
    except Exception:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_ui_window()
        if hwnd:
            try:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
                startup_log("UI started minimized to the tray")
                if tray:
                    # Um aviso, uma vez. O cliente precisa saber onde o app foi
                    # parar; repetir isso a cada abertura viraria ruido.
                    tray.notify("AZOR Optimization",
                                "O AZOR abriu em segundo plano. Clique neste icone para ver a tela.")
                return True
            except Exception as exc:
                startup_log(f"Could not hide UI window: {exc}")
                return False
        time.sleep(0.35)
    startup_log("UI window did not appear in time to be minimized")
    return False


# ---------------------------------------------------------------------------
# Instancia unica e saida limpa
#
# O bug que isto conserta: o launcher encerra o backend antigo com
# `Stop-Process -Force`, que e TerminateProcess. O processo morre sem executar
# nada - inclusive sem o Shell_NotifyIcon(NIM_DELETE) que remove o icone da
# bandeja. O Windows mantem o icone orfao ate alguem passar o mouse por cima,
# entao CADA abertura deixava mais um "AZOR" ali. Nao eram varios apps rodando:
# era um app e varios fantasmas.
#
# A correcao tem duas metades. Aqui, o backend passa a escutar um evento nomeado
# e a sair com dignidade quando ele e sinalizado. No launcher, o pedido educado
# vem ANTES do encerramento forcado, que continua existindo so como rede.
QUIT_EVENT_NAME = "Local\\AzorOptimizationQuit"


def _open_quit_event(create: bool):
    if os.name != "nt":
        return None
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        if create:
            handle = k32.CreateEventW(None, True, False, QUIT_EVENT_NAME)
        else:
            EVENT_MODIFY_STATE = 0x0002
            handle = k32.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT_NAME)
        return handle or None
    except Exception:
        return None


def signal_running_instance() -> bool:
    """Pede ao AZOR que ja estiver aberto para encerrar sozinho."""
    handle = _open_quit_event(create=False)
    if not handle:
        return False
    try:
        import ctypes
        ctypes.windll.kernel32.SetEvent(handle)
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


def watch_quit_event(server, tray) -> None:
    """Espera o pedido de saida e encerra limpo - com o icone removido."""
    handle = _open_quit_event(create=True)
    if not handle:
        return
    try:
        import ctypes
        # WaitForSingleObject bloqueia esta thread e so ela; INFINITE porque o
        # processo inteiro morre logo depois.
        ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        startup_log("Quit requested by a newer instance; shutting down cleanly")
        try:
            if tray:
                tray.stop()
        except Exception:
            pass
        threading.Thread(target=server.shutdown, daemon=True).start()
    except Exception as exc:
        startup_log(f"Quit watcher failed: {exc}")


def quit_running_instance(wait_seconds: float = 6.0) -> bool:
    """Modo `--quit-running`: sinaliza e espera o processo antigo sumir.

    Se o evento nao existe MAS o runtime aponta um PID vivo, a resposta honesta e
    False: nao ha nada a sinalizar e o processo continua la. Dizer "ok" ali fazia
    o launcher seguir achando que a porta estava livre.
    """
    if not signal_running_instance():
        info = read_runtime() or {}
        pid = int(info.get("pid") or 0)
        if pid and _pid_alive(pid) and pid != os.getpid():
            startup_log(f"Quit requested but no listener; pid {pid} still alive")
            return False
        return True  # nada rodando
    deadline = time.time() + max(1.0, wait_seconds)
    while time.time() < deadline:
        info = read_runtime() or {}
        pid = int(info.get("pid") or 0)
        if not pid or not _pid_alive(pid):
            return True
        time.sleep(0.25)
    return False


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


def open_ui(url, minimized=False, tray=None):
    # Always open this exact backend with a unique URL. This prevents Edge or an
    # old AZOR window from visually reusing a previous UI.
    launch_url = f"{url.rstrip('/')}?azor_build={_build_id()}&ui=2d&fp={_ui_fingerprint()}&t={int(time.time()*1000)}"
    # Important: the backend lifetime must NOT depend on the Edge launcher process.
    # Edge can hand the URL to an existing process and make Popen return immediately.
    # Older builds interpreted that as "the app was closed" and shut down localhost.
    ready = False
    for _ in range(24):
        ok, _ = probe_url(url, timeout=0.6)
        if ok:
            ready = True
            break
        time.sleep(0.25)
    if not ready:
        startup_log(f"UI launch aborted because backend did not answer: {url}")
        return False
    try:
        edge = find_edge()
        if edge:
            # Never reuse the profile used by legacy AZOR windows. A build-specific
            # isolated Edge profile guarantees that the window opened by this server
            # belongs to this exact payload and cannot visually reuse the old 3D app.
            safe_build = "".join(ch if ch.isalnum() else "_" for ch in _build_id())[-72:] or "current"
            profile = os.path.join(os.environ.get("LOCALAPPDATA", str(ROOT)), "AzorOptimization", f"edge_current_2d_{safe_build}")
            subprocess.Popen([
                edge, f"--app={launch_url}",
                *([] if minimized else ["--start-maximized"]),
                "--no-first-run", "--no-default-browser-check",
                f"--user-data-dir={profile}", "--disable-extensions", "--new-window",
                "--disable-features=msEdgeSidebarV2,msEdgeShoppingAssistant"
            ])
            startup_log(f"Edge UI requested at {launch_url}")
            if minimized:
                threading.Thread(target=hide_ui_window, args=(tray,), daemon=True).start()
            return True
    except Exception as e:
        startup_log(f"Edge app mode launch failed: {e}")
        core.log(f"Edge app mode launch failed: {e}")
    try:
        opened = bool(webbrowser.open(launch_url))
        startup_log(f"Default browser requested at {launch_url}; opened={opened}")
        return opened
    except Exception as e:
        startup_log(f"Default browser launch failed: {e}")
        return False


def warm_caches() -> None:
    """Pre-reads what the first screen needs, off the request path."""
    try:
        core.system_summary()
    except Exception as e:
        core.log(f"warmup summary failed: {e}")
    try:
        core.monitor_snapshot()
    except Exception as e:
        core.log(f"warmup monitor failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    # Permite forcar o comportamento pela linha de comando, independentemente da
    # preferencia salva - util para um atalho "AZOR em segundo plano".
    parser.add_argument("--minimized", action="store_true")
    # Chamado pelo launcher antes do encerramento forcado, para o AZOR antigo
    # remover o proprio icone da bandeja em vez de virar fantasma.
    parser.add_argument("--quit-running", action="store_true")
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe-runtime", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=12.0)
    args = parser.parse_args()
    if args.self_test:
        raise SystemExit(0 if run_self_test().get("ok") else 31)
    if args.quit_running:
        ok = quit_running_instance(args.wait_seconds if args.wait_seconds else 6.0)
        print(json.dumps({"ok": ok}, ensure_ascii=False))
        raise SystemExit(0)
    if args.probe_runtime:
        ok, info = wait_runtime(args.wait_seconds)
        print(json.dumps({"ok": ok, **(info or {})}, ensure_ascii=False))
        raise SystemExit(0 if ok else 41)

    # Always start a fresh backend for the files in this extracted folder.
    DATA.mkdir(parents=True, exist_ok=True)
    startup_log(f"Starting Azor backend build={_build_id()} python={sys.executable}")
    bind_port = int(args.port) if int(args.port or 0) > 0 else 0
    server = ThreadingHTTPServer(("127.0.0.1", bind_port), Handler)
    server.daemon_threads = True
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/"
    write_runtime(url, port)
    startup_log(f"Backend bound successfully: {url} pid={os.getpid()}")
    core.log(f"Azor local UI started at {url}")
    # Session controls are explicit. Opening never launches the legacy reapplication agent.
    # "Aplicou = fica": antes de qualquer coisa, reconfere o que ja foi aplicado e
    # devolve ao lugar o que o Windows mexeu desde a ultima sessao. Vai numa
    # thread para nao segurar a abertura da janela.
    if os.environ.get("AZOR_TEST_MODE") != "1":
        threading.Thread(target=core.run_startup_reconcile, name="azor-reconcile", daemon=True).start()
    # Uma gravacao interrompida (queda de energia, kill -9 do launcher) deixa o
    # temporario para tras. Agora eles tem nome unico por chamada, entao nao
    # colidem mais - mas acumulariam em data/ sem alguem para varrer.
    try:
        swept = core._sweep_stale_tmp()
        if swept:
            core.log(f"Limpeza: {swept} temporario(s) orfao(s) removido(s) de data/.")
    except Exception:
        pass
    # Edge takes a second or two to start and paint. Filling the summary cache in
    # parallel means the first screen the user sees already has real data instead
    # of waiting ~3,4 s for the first cold read.
    threading.Thread(target=warm_caches, name="azor-warmup", daemon=True).start()
    # Icone da bandeja: o AZOR passa a viver ao lado do relogio. Minimizar recolhe
    # a janela para la, e o menu do botao direito e o unico jeito honesto de
    # encerrar de verdade um app cuja interface e uma janela do Edge.
    tray = None
    if not args.no_browser and os.name == "nt":
        try:
            from azor_tray import AzorTray
            tray = AzorTray(
                icon_path=WEB / "assets" / "Azor.ico",
                tooltip="AZOR Optimization",
                on_open=lambda: open_ui(url),
                # shutdown() precisa vir de outra thread que nao a do serve_forever,
                # e a thread da bandeja e exatamente isso.
                on_exit=lambda: threading.Thread(target=server.shutdown, daemon=True).start(),
                log=core.log,
            )
            if tray.start():
                startup_log("Tray icon started")
        except Exception as exc:
            startup_log(f"Tray icon unavailable: {exc}")
            core.log(f"Tray icon unavailable: {exc}")
    # O vigia de saida limpa NAO depende da bandeja: ele e sobre o processo.
    # Amarrado ao tray, um backend iniciado com --no-browser ficava surdo ao
    # pedido de saida - e dois deles terminavam na mesma porta, com o antigo
    # respondendo (allow_reuse_address permite isso no Windows). Foi assim que o
    # catalogo apareceu com 68 itens na tela e 70 no disco.
    threading.Thread(target=watch_quit_event, args=(server, tray),
                     name="azor-quit-watch", daemon=True).start()

    if not args.no_browser:
        minimized = args.minimized or (core.should_start_minimized() and not args.visible)
        threading.Thread(target=open_ui, args=(url, minimized, tray), daemon=True).start()
        core.mark_first_launch()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if tray:
                tray.stop()
        except Exception:
            pass
        try:
            core.GAME_PRIORITY.stop()
        except Exception as exc:
            core.log('Game session recovery pending: '+str(exc))
        try:
            core.TIMER_SESSION.disable()
        except Exception:
            pass
        try:
            input_monitor.stop()
        except Exception:
            pass
        try:
            gamepad_monitor.stop()
        except Exception:
            pass
        try:
            # The sampler owns a long-lived nvidia-smi; it must not outlive us.
            core.MONITOR_SAMPLER.stop()
        except Exception:
            pass
        server.server_close()
        try:
            current = read_runtime()
            if int(current.get("pid") or -1) == os.getpid() and RUNTIME_FILE.exists():
                RUNTIME_FILE.unlink()
        except Exception:
            pass
        startup_log(f"Backend stopped pid={os.getpid()}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        startup_log("FATAL: " + repr(e))
        startup_log(traceback.format_exc())
        try:
            core.log("Azor server fatal startup error: " + traceback.format_exc())
        except Exception:
            pass
        raise
