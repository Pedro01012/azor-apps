"""AZOR game sessions: explicit profiles, reversible priority and optional power switching."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import re
import threading
import time
from azor_modules.transactions import read,save,restore
from azor_managers import PowerManager

DEFAULT_PROFILES=[
 {'id':'fortnite','name':'Fortnite','exe':'FortniteClient-Win64-Shipping.exe','priority':'above_normal','power_guid':None},
 {'id':'valorant','name':'Valorant','exe':'VALORANT-Win64-Shipping.exe','priority':'above_normal','power_guid':None},
 {'id':'cs2','name':'CS2','exe':'cs2.exe','priority':'above_normal','power_guid':None},
 {'id':'minecraft','name':'Minecraft Java','exe':'javaw.exe','path_contains':'.minecraft','priority':'normal','power_guid':None},
]
PRIORITIES={'normal':0x20,'above_normal':0x8000,'high':0x80}
OPTIONAL_BACKGROUND=frozenset(('discord.exe','spotify.exe','ms-teams.exe','teams.exe','onedrive.exe'))
PROTECTED=frozenset(('system','registry','smss.exe','csrss.exe','wininit.exe','winlogon.exe','services.exe','lsass.exe','dwm.exe','explorer.exe','svchost.exe','audiodg.exe','msmpeng.exe','nissrv.exe','securityhealthservice.exe','vgc.exe','vgtray.exe','easyanticheat.exe','easyanticheat_eos.exe','beservice.exe','nvcontainer.exe','nvidia share.exe','rzsynapse.exe','lghub.exe','icue.exe','azor optimization completo.exe'))

class GameProcessManager:
    def __init__(self,core):
        self.core=core;self._stop=threading.Event();self._thread=None;self._lock=threading.RLock()
        self._owned={};self._power=None;self._persisted=None;self._power_attempt=None;self.applied=0;self.last_status='Desativado.'
        self.operation_lock=threading.RLock()
        self._state={'games':[],'cpu_percent':None,'memory':{},'process_count':None}
        self.file=core.DATA_DIR/'game_session.json';self.profile_file=core.DATA_DIR/'game_profiles.json'
        self._recovery_error=False
        try:
            previous=read(self.file)
            self._owned={int(r['pid']):r for r in previous.get('processes',[])}
            for row in self._owned.values():
                if type(row['created']) is not int or type(row['priority']) is not int or type(row['target']) is not int:raise ValueError('Invalid session')
            self._power=previous.get('power')
            if self._power and not all(self._power.get(k) for k in ('transaction_id','applied')):raise ValueError('Invalid power session')
        except FileNotFoundError:pass
        except (ValueError,KeyError,TypeError,OSError):
            self._recovery_error=True;self.last_status='Registro anterior ilegível; preservado para revisão.'
    def running(self):return bool(self._thread and self._thread.is_alive())
    def profiles(self):
        try:config=read(self.profile_file)
        except FileNotFoundError:config={'profiles':copy.deepcopy(DEFAULT_PROFILES),'background':[]}
        if not isinstance(config,dict) or not isinstance(config.get('profiles'),list):raise ValueError('GAME_PROFILES_UNREADABLE')
        return config
    def configure(self,profiles,background):
        if self.running() or self._owned or self._power:raise ValueError('Pare e restaure o modo de jogo antes de editar os perfis.')
        if not isinstance(profiles,list) or not 1<=len(profiles)<=24:raise ValueError('GAME_PROFILES_INVALID')
        ids=set();out=[]
        for row in profiles:
            id=str(row.get('id',''));exe=str(row.get('exe',''));priority=row.get('priority','normal')
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,50}',id) or id in ids:raise ValueError('GAME_ID_INVALID')
            if not re.fullmatch(r'[^\\/:*?"<>|]{1,150}\.exe',exe,re.I) or exe.lower() in PROTECTED:raise ValueError('GAME_EXECUTABLE_PROTECTED')
            if priority not in PRIORITIES:raise ValueError('GAME_PRIORITY_INVALID')
            guid=row.get('power_guid') or None
            if guid:PowerManager(self.core)._guid(guid)
            ids.add(id);out.append({'id':id,'name':str(row.get('name') or id)[:100],'exe':exe,
                'path_contains':str(row.get('path_contains') or '')[:260],'priority':priority,'power_guid':guid})
        if not isinstance(background,list) or not set(background)<=OPTIONAL_BACKGROUND:raise ValueError('BACKGROUND_PROCESS_PROTECTED')
        save(self.profile_file,{'profiles':out,'background':background})
        return {'ok':True,'detail':'Perfis salvos. Afinidade permanece com o agendador do Windows.','profiles':out}
    def status(self):
        with self._lock:
            return {'supported':os.name=='nt','running':self.running(),'raised':len(self._owned),'applied':self.applied,
                    'last_status':self.last_status,**copy.deepcopy(self._state),
                    'profiles':self.profiles(),'background_options':sorted(OPTIONAL_BACKGROUND),
                    'recovery_required':bool(self._recovery_error or self._owned or self._power) and not self.running(),
                    'policy':'Nenhum processo é encerrado. Só processos escolhidos podem ter prioridade temporária; afinidade, segurança e anti-cheat são preservados.'}
    def _persist(self):
        state={'processes':list(self._owned.values()),'power':self._power}
        if state!=self._persisted:
            save(self.file,state);self._persisted=copy.deepcopy(state)
    def _protected(self,info):
        name=str(info.get('name','')).lower();path=str(info.get('path','')).casefold()
        windows=str(os.environ.get('SystemRoot',r'C:\Windows')).casefold().rstrip('\\')+'\\'
        return name in PROTECTED or info.get('pid') in (0,4,os.getpid()) or path.startswith(windows) or any(x in path for x in ('vanguard','easyanticheat','battleye','windows defender'))
    def _change(self,info,target,role):
        if self._protected(info) or info['priority']==target:return
        if info['pid'] in self._owned:return
        if role=='background' and info['priority']!=0x20:return
        if role=='game' and info['priority'] in (0x80,0x100):return
        entry={**info,'target':target,'role':role}
        self._owned[info['pid']]=entry
        try:self._persist()
        except Exception:
            self._owned.pop(info['pid'],None);raise
        if self.core.set_process_priority(info['pid'],target,info['created']):
            self.applied+=1;self.last_status='Prioridade temporária aplicada e relida.'
            self.core.journal('game_priority_applied',pid=info['pid'],role=role)
        else:
            self.last_status='GAME_PRIORITY_ACCESS_DENIED: processo protegido ou alteração não confirmada.'
            self._restore_process(info['pid'])
    def _restore_process(self,pid):
        entry=self._owned[pid];now=self.core.process_snapshot(pid)
        if now is None:
            # Access denied is not proof that a process exited. Keep recovery data.
            if any(int(p)==pid for name,p in self.core._process_list()):return False
            self._owned.pop(pid,None);return True
        if now['created']!=entry['created']:
            self._owned.pop(pid,None);return True
        if now['priority']!=entry['target']:
            # A game or the user changed its own priority after us. Do not override it.
            self._owned.pop(pid,None);return True
        if self.core.set_process_priority(pid,entry['priority'],entry['created']):
            self._owned.pop(pid,None);self.core.journal('game_priority_restored',pid=pid)
            return True
        return False
    def _restore_power(self):
        if not self._power:return True
        active=self.core.get_active_power_scheme()
        if not active:return False
        if active!=self._power['applied']:
            self._power=None;return True
        result=restore(self.core,self._power['transaction_id'])
        if result['ok']:self._power=None
        return result['ok']
    def _restore_all(self):
        if self._recovery_error:return False
        ok=True
        for pid in list(self._owned):ok=self._restore_process(pid) and ok
        try:ok=self._restore_power() and ok
        except Exception as exc:ok=False;self.last_status=str(exc)
        self._persist()
        return ok
    def start(self):
        if os.name!='nt':return False,'Modo de jogo disponível no Windows.'
        if self.running():return True,'Modo de jogo já está ativo.'
        # Recover a previous session only after this explicit Start action.
        try:
            previous=read(self.file)
            self._owned={int(r['pid']):r for r in previous.get('processes',[])};self._power=previous.get('power')
        except FileNotFoundError:pass
        except (ValueError,KeyError,TypeError,OSError):return False,'GAME_SESSION_UNREADABLE: registro anterior preservado; confira o histórico.'
        if not self._restore_all():return False,'Restauração anterior pendente. Não será iniciada outra sessão.'
        self._stop.clear();self._thread=threading.Thread(target=self._loop,name='azor-game-mode',daemon=True)
        self._thread.start();return True,'Modo de jogo ativo. Aguardando um executável do perfil.'
    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():self._thread.join(5)
        if self.running():return False,'Finalizando a leitura atual; restauração será concluída em seguida.'
        with self._lock:
            ok=self._restore_all();self.last_status='Sessão encerrada e estado anterior restaurado.' if ok else 'Restauração ainda precisa de atenção.'
        return ok,self.last_status
    def tick(self):
        config=self.profiles();processes=list(self.core._process_list());games=[]
        candidates={str(name).lower():[] for name,pid in processes}
        for name,pid in processes:candidates[str(name).lower()].append(pid)
        for profile in config['profiles']:
            for pid in candidates.get(profile['exe'].lower(),[]):
                info=self.core.process_snapshot(pid)
                if not info or self._protected(info):continue
                needle=profile.get('path_contains','').casefold()
                if needle and needle not in info['path'].casefold():continue
                games.append({**info,'profile':profile['id'],'game':profile['name'],
                    'priority_target':profile['priority'],'power_guid':profile.get('power_guid')})
        alive={g['pid'] for g in games}
        for pid,entry in list(self._owned.items()):
            if entry['role']=='game' and pid not in alive:self._restore_process(pid)
        cpu=self.core._cpu_usage_windows() if games else None
        memory=self.core._memory_windows() if games else {}
        self._state={'games':[{'pid':g['pid'],'name':g['game'],'profile':g['profile'],'priority':g['priority_target']} for g in games],
                     'cpu_percent':cpu,'memory':memory,'process_count':len(processes)}
        if not games:
            self._power_attempt=None
            self._restore_all();self.last_status='Aguardando jogo; políticas do sistema preservadas.'
            return
        for game in games:self._change(game,PRIORITIES[game['priority_target']],'game')
        chosen_power=next((g.get('power_guid') for g in games if g.get('power_guid')),None)
        if chosen_power and not self._power and self._power_attempt!=chosen_power and self.core.get_active_power_scheme()!=chosen_power:
            self._power_attempt=chosen_power
            def prepared(transaction_id):
                self._power={'transaction_id':transaction_id,'applied':chosen_power};self._persist()
            result=PowerManager(self.core).apply_plan(chosen_power,on_prepared=prepared)
            if not result['ok']:
                self.last_status=result.get('detail','POWER_SESSION_FAILED')
                if (result.get('rollback') or {}).get('ok'):self._power=None
        if isinstance(cpu,(int,float)) and cpu>=80:
            for name in config.get('background',[]):
                for pid in candidates.get(name,[]):
                    info=self.core.process_snapshot(pid)
                    if info:self._change(info,0x4000,'background')
        elif isinstance(cpu,(int,float)) and cpu<60:
            for pid,entry in list(self._owned.items()):
                if entry['role']=='background':self._restore_process(pid)
        self._persist()
    def _loop(self):
        try:
            while not self._stop.is_set():
                try:
                    if self.operation_lock.acquire(timeout=.2):
                        try:
                            with self._lock:self.tick()
                        finally:self.operation_lock.release()
                except Exception as exc:self.last_status='GAME_SESSION_ERROR: '+str(exc)
                self._stop.wait(3)
        finally:
            # stop() can own the operation lock. In that case it restores after join.
            if self.operation_lock.acquire(timeout=.2):
                try:
                    with self._lock:self._restore_all()
                except Exception as exc:self.last_status='GAME_RESTORE_FAILED: '+str(exc)
                finally:self.operation_lock.release()
