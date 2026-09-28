from __future__ import annotations
import os, sys, time, traceback
from pathlib import Path
import azor_core as core

ROOT=Path(__file__).resolve().parent

def write_state(**kw):
    st=core._safe_json_read(core.AGENT_STATE_FILE,{})
    if not isinstance(st,dict): st={}
    st.update(kw); core._safe_json_write(core.AGENT_STATE_FILE,st)

def already_running():
    st=core.agent_status()
    return bool(st.get('running') and int(st.get('pid') or 0)!=os.getpid())

def main():
    if already_running(): return
    write_state(pid=os.getpid(),started_at=core._ts(),heartbeat=core._ts(),status='running',game_active=False,last_error=None)
    core.log(f"Azor Guardian agent started pid={os.getpid()}")
    last_guard=0.0; last_maint_check=0.0; last_islc_try=0.0; prev_game=False; last_written=None
    while True:
        try:
            now=time.time(); settings=core.load_settings(); gm=core.game_monitor_snapshot(); game=bool(gm.get('running'))
            timer_enabled=bool(settings.get('latency_engine_autostart',True))
            timer_game_only=bool(settings.get('latency_engine_game_only',True))
            timer_should_run=timer_enabled and (game or not timer_game_only)
            if timer_should_run:
                target=float(settings.get('latency_target_ms',0.5) or 0.5)
                if (not core.TIMER_SESSION.active) or abs(float(core.TIMER_SESSION.requested_ms)-target)>0.01:
                    ok,detail=core.TIMER_SESSION.enable(target); core.log('Latency Engine startup/update: '+detail)
                tq=core.TIMER_SESSION.query()
                write_state(timer_active=core.TIMER_SESSION.active,timer_requested_ms=target,timer_actual_ms=tq.get('actual_ms'),timer_mode=core.TIMER_SESSION.mode,timer_scope='game-only' if timer_game_only else 'always')
            elif core.TIMER_SESSION.active:
                ok,detail=core.TIMER_SESSION.disable(); core.log('Latency Engine released because current policy does not require it: '+detail)
                write_state(timer_active=False,timer_actual_ms=None,timer_mode='off',timer_scope='game-only' if timer_game_only else 'disabled')

            if settings.get('guardian_enabled',True) and now-last_guard>=60:
                health=core.guardian_check_once(); last_guard=now
                write_state(last_guardian=core._ts(),last_guardian_ok=health.get('ok'))
            if settings.get('game_monitor_enabled',True):
                if game and not prev_game:
                    core.log(f"Game Monitor entered gaming state: {gm.get('games')}")
                    if settings.get('power_enforcement',True): core.set_azor_fps_boost_power()
                    if settings.get('persistent_game_mode',True): core.set_game_mode_verified(True)
                    if settings.get('islc_autostart',True) and now-last_islc_try>60:
                        core.ensure_external_islc_running(); last_islc_try=now
                elif prev_game and not game:
                    core.log("Game Monitor left gaming state.")
            prev_game=game
            if settings.get('daily_maintenance_enabled',True) and now-last_maint_check>=1800:
                last_maint_check=now; ms=core.maintenance_status(); last=core._safe_json_read(core.MAINTENANCE_FILE,{})
                due=not last.get('last_run')
                if last.get('last_run'):
                    try:
                        last_ts=time.mktime(time.strptime(last['last_run'],'%Y-%m-%d %H:%M:%S')); due=now-last_ts>=20*3600
                    except Exception: due=True
                if due and not game:
                    r=core.daily_maintenance(False);write_state(last_maintenance_result=r.get('status'),last_maintenance=core._ts())
            if settings.get('islc_autostart',True) and settings.get('islc_watchdog',True) and now-last_islc_try>=120:
                info=core.detect_external_islc_process(); game_only=bool(settings.get('islc_game_only',True))
                if info.get('found') and not info.get('running') and (game or not game_only):
                    core.ensure_external_islc_running(); last_islc_try=now
            # A cadencia estava invertida: o agente acordava MAIS vezes (5 s)
            # justamente durante a partida, que e quando ele precisa sumir. Cada
            # volta relia as configuracoes do disco, tirava um retrato dos
            # processos e reescrevia um JSON - no meio do jogo.
            #
            # Agora o retrato so e reescrito quando algo mudou de verdade, e
            # jogando o intervalo sobe para 20 s. O que precisa ser rapido - o
            # jogo ganhou foco? - passou a ser respondido pela janela em primeiro
            # plano, que custa ~60 us e nao enumera nada.
            state = {'pid': os.getpid(), 'status': 'running', 'game_active': game,
                     'games': gm.get('games', [])}
            if state != last_written:
                write_state(heartbeat=core._ts(), **state)
                last_written = state
            else:
                write_state(heartbeat=core._ts())
            time.sleep(20 if game else 15)
        except KeyboardInterrupt: break
        except Exception as e:
            core.log(f"Guardian loop error: {e}\n{traceback.format_exc()}");write_state(last_error=str(e),heartbeat=core._ts());time.sleep(20)
    try:
        core.TIMER_SESSION.disable()
    except Exception:
        pass
    write_state(status='stopped',stopped_at=core._ts())

if __name__=='__main__': main()
