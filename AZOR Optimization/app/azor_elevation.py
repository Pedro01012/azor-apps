"""Eleva só a operação pedida; a interface continua como usuário comum.

Quando o AZOR já foi aberto como administrador (o launcher pede isso uma vez),
tudo roda direto, sem nenhum aviso extra do Windows.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from azor_modules.transactions import read,save

TASK_ID=r'[a-z0-9_]{2,64}'
APP_ID=r'[a-z0-9_]{2,40}'
PACKAGE=r'[A-Za-z0-9._-]{2,120}'
FIXES=('system','network','update','legacy_games','restore_point','winget','recycle_bin','deep_cleanup')

OPERATIONS={'boost','apply_task','revert_task','apply_tasks','revert_tasks','restore_all','undo_everything',
            'restore_transaction','logon_autoapply','apps_install','apps_uninstall','apps_upgrade','appx_remove',
            'cleanup','startup_set','startup_bulk','fix','compat_fix','dns_set','usb_irq','firmware_reboot'}


def _ids(request,key,pattern,limit=200):
    ids=request.get(key)
    if not isinstance(ids,list) or not 1<=len(ids)<=limit or any(not re.fullmatch(pattern,str(i)) for i in ids):
        raise ValueError(key.upper()+'_INVALID')
    return [str(i) for i in ids]


def validate(request):
    if not isinstance(request,dict) or request.get('operation') not in OPERATIONS:
        raise ValueError('OPERATION_INVALID')
    op=request['operation']
    if op=='boost' and request.get('mode') not in ('maximo','agressivo'):
        raise ValueError('MODE_INVALID')
    if op in ('apply_task','revert_task') and not re.fullmatch(TASK_ID,str(request.get('id',''))):
        raise ValueError('TASK_INVALID')
    if op in ('apply_tasks','revert_tasks'):
        _ids(request,'ids',TASK_ID)
    if op=='restore_all' and request.get('target','baseline') not in ('baseline','last'):
        raise ValueError('TARGET_INVALID')
    if op=='logon_autoapply' and (not isinstance(request.get('enabled'),bool) or request.get('profile','maximo') not in ('maximo','agressivo')):
        raise ValueError('LOGON_INVALID')
    if op in ('apps_install','apps_uninstall'):
        _ids(request,'ids',APP_ID,80)
    if op=='appx_remove':
        _ids(request,'packages',PACKAGE,80)
    if op=='cleanup':
        _ids(request,'ids',r'[a-z_]{2,40}',20)
    if op=='startup_set' and (request.get('scope') not in ('HKCU_RUN','HKLM_RUN','HKLM_RUN32','HKCU_FOLDER','HKLM_FOLDER')
                              or not isinstance(request.get('enabled'),bool) or not str(request.get('name') or '').strip()):
        raise ValueError('STARTUP_INVALID')
    if op=='startup_bulk' and not isinstance(request.get('extreme'),bool):
        raise ValueError('STARTUP_INVALID')
    if op=='fix' and request.get('kind') not in FIXES:
        raise ValueError('FIX_INVALID')
    if op=='compat_fix' and not re.fullmatch(r'[a-z_]{2,30}',str(request.get('id',''))):
        raise ValueError('CHECK_INVALID')
    if op=='dns_set' and request.get('provider') not in ('auto','cloudflare','google','quad9','adguard'):
        raise ValueError('DNS_INVALID')
    if op=='restore_transaction' and not re.fullmatch(r'[a-f0-9-]{36}',str(request.get('id',''))):
        raise ValueError('TRANSACTION_INVALID')
    if op=='usb_irq' and not isinstance(request.get('enabled'),bool):
        raise ValueError('USB_IRQ_INVALID')
    if op=='firmware_reboot' and not (isinstance(request.get('delay'),int) and 5<=request['delay']<=120):
        raise ValueError('DELAY_INVALID')
    return request


def _batch(rows,verb):
    done=sum(1 for r in rows if r.get('ok'))
    return {'ok':done==len(rows),'results':rows,'detail':f'{done} de {len(rows)} ajuste(s) {verb} e relido(s).'}


def undo_everything(core,progress=None):
    """Volta o PC para como estava antes do AZOR: registro, energia, tarefas, boot e login."""
    from azor_modules import engine,startup
    say=progress or (lambda *a:None)
    say('Registro e energia','applying','Restaurando o estado anterior ao AZOR…')
    report=core.restore_all_report('baseline')
    extra=[]
    for task_id in ('visual_effects','telemetry_tasks_off','classic_context_menu','reserved_storage_off',
                    'hibernate_off','display_max_refresh','nvme_idle_never','nic_power_saving_off',
                    'nic_green_ethernet_off','nic_rss_on','nic_interrupt_moderation_off','nagle_off',
                    'ntfs_last_access_off','ntfs_short_names_off','memory_compression_off','defender_game_exclusions',
                    'usb_hub_power_off','gpu_interrupt_priority','all_games_gpu','fortnite_gpu','fortnite_fullscreen_exclusive'):
        if task_id in set(core.desired_task_ids()):
            say(task_id,'applying','Desfazendo…')
            extra.append(engine.revert_task(task_id))
    boot=startup.restore_disabled(core)
    say('Inicialização','completed',f"{len(boot.get('restored',[]))} programa(s) de volta ao boot.")
    try:
        import azor_autostart
        azor_autostart.uninstall(core)
    except Exception:
        pass
    ok=bool(report.get('ok')) and all(r.get('ok') for r in extra) and boot.get('ok')
    return {'ok':ok,'detail':('Tudo voltou para como estava antes do AZOR. Reinicie o PC.' if ok else
                              'A maior parte voltou; veja os itens que falharam e reinicie o PC.'),
            'results':report.get('results',[])+[{'name':r.get('name') or r.get('id'),'status':'completed' if r.get('ok') else 'failed','detail':r.get('detail')} for r in extra],
            'restart':True}


def execute_local(core,request,progress=None):
    from azor_modules import engine,transactions,boost,apps,debloat,cleanup,startup,fixes,gamecompat
    validate(request);op=request['operation']
    if op=='boost':
        return boost.run(core,request['mode'],request.get('options') or {},progress)
    if op=='apply_task':return engine.apply_task(str(request.get('id','')),'agressivo')
    if op=='revert_task':return core.revert_optimization(str(request.get('id','')))
    if op=='apply_tasks':
        ids=_ids(request,'ids',TASK_ID)
        rows=engine.execute('agressivo',progress=progress,task_ids=ids)
        backup=next((r for r in rows if r.get('name')=='Backup / Restore'),{})
        if backup.get('status')!='completed':
            return {'ok':False,'results':rows,'detail':'Backup não confirmado; nada foi alterado.'}
        picked=[r for r in rows if r.get('id')]
        done=sum(1 for r in picked if r.get('status')=='completed')
        return {'ok':done==len(picked),'results':picked,'restart':any(r.get('restart') for r in picked),
                'detail':f'{done} de {len(picked)} ajuste(s) aplicado(s) e relido(s).'}
    if op=='revert_tasks':
        return _batch([core.revert_optimization(str(i)) for i in request['ids']],'desfeito(s)')
    if op=='restore_all':return core.restore_all_report(str(request.get('target','baseline')))
    if op=='undo_everything':return undo_everything(core,progress)
    if op=='restore_transaction':return transactions.restore(core,str(request.get('id','')))
    if op=='logon_autoapply':
        import azor_autostart
        if request['enabled']:return azor_autostart.install(core,request.get('profile','maximo'),progress)
        return azor_autostart.uninstall(core)
    if op=='apps_install':return apps.install(core,request['ids'],progress)
    if op=='apps_uninstall':return apps.uninstall(core,request['ids'],progress)
    if op=='apps_upgrade':return apps.upgrade_all(core,progress)
    if op=='appx_remove':return debloat.remove(core,request['packages'],progress)
    if op=='cleanup':return cleanup.clean(core,request['ids'],progress)
    if op=='startup_set':
        ok,detail=startup.set_enabled(core,request['scope'],str(request['name']),request['enabled'])
        return {'ok':ok,'detail':detail}
    if op=='startup_bulk':
        res=startup.boost_disable(core,request['extreme'],progress)
        n=len(res.get('disabled',[]))
        return {'ok':res.get('ok',False),'detail':f'{n} programa(s) tirado(s) do boot.' if n else 'Nada para desligar.',
                'results':[{'name':x,'ok':False,'detail':'Não confirmado.'} for x in res.get('failed',[])]}
    if op=='fix':
        kind=request['kind']
        if kind=='system':return fixes.system_repair(core,progress)
        if kind=='network':return fixes.network_reset(core,progress)
        if kind=='update':return fixes.update_reset(core,progress)
        if kind=='legacy_games':return fixes.legacy_games(core,progress)
        if kind=='winget':return apps.repair_winget(core,progress)
        if kind=='recycle_bin':return cleanup.empty_recycle_bin(core)
        if kind=='deep_cleanup':return cleanup.deep_component_cleanup(core,progress)
        ok,detail=core.create_windows_restore_point('AZOR - antes de otimizar')
        return {'ok':ok,'detail':detail}
    if op=='compat_fix':return gamecompat.fix(core,str(request['id']),progress)
    if op=='dns_set':return fixes.dns_set(core,request['provider'])
    if op=='usb_irq':
        ok,detail=(core.set_usb_interrupts_on_ecores_verified() if request['enabled'] else core.usb_interrupt_affinity_revert())
        return {'ok':ok,'detail':detail,'restart':ok}
    if op=='firmware_reboot':return core.reboot_to_firmware(request['delay'])
    raise ValueError('OPERATION_INVALID')


def _task_needs_admin(task):
    """So dispensa o UAC quando o item grava apenas chaves do próprio usuário."""
    if task is None:
        return False
    keys=tuple(task.registry_keys or ())
    user_only=bool(keys) and all(str(k[0]).upper()=='HKCU' for k in keys) and not task.power_changes
    return bool(task.requires_admin) or not user_only


def needs_admin(core,request):
    from azor_modules import engine,cleanup
    op=request['operation']
    if op=='restore_transaction':
        id=str(request.get('id',''))
        if not re.fullmatch(r'[a-f0-9-]{36}',id):raise ValueError('TRANSACTION_INVALID')
        item=read(core.DATA_DIR/'transactions'/(id+'.json'))
        return item.get('requires_admin') or item['before']['kind']!='registry' or any(e['root']=='HKLM' for e in item['before'].get('entries',[]))
    if op=='startup_set':
        return request.get('scope') in ('HKLM_RUN','HKLM_RUN32','HKLM_FOLDER')
    if op=='cleanup':
        wanted=set(request.get('ids') or [])
        return any(t['admin'] for t in cleanup.targets() if t['id'] in wanted)
    if op in ('apply_task','revert_task','apply_tasks','revert_tasks'):
        by_id={t.id:t for t in engine._all_tasks()}
        ids=[request.get('id')] if op in ('apply_task','revert_task') else list(request.get('ids') or [])
        return any(_task_needs_admin(by_id.get(i)) for i in ids)
    return True


def user_sid(core):
    p=core.run_hidden(['whoami','/user','/fo','csv','/nh'],timeout=10)
    match=re.search(r'S-1-[0-9]+-(?:[0-9]+-)*[0-9]+',p.stdout or '')
    if p.returncode or not match:raise ValueError('USER_IDENTITY_UNAVAILABLE')
    return match.group(0)

class SHELLEXECUTEINFO(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('fMask',wintypes.ULONG),('hwnd',wintypes.HWND),
        ('lpVerb',wintypes.LPCWSTR),('lpFile',wintypes.LPCWSTR),('lpParameters',wintypes.LPCWSTR),
        ('lpDirectory',wintypes.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',wintypes.HINSTANCE),
        ('lpIDList',ctypes.c_void_p),('lpClass',wintypes.LPCWSTR),('hkeyClass',wintypes.HKEY),
        ('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),('hProcess',wintypes.HANDLE)]

def run_action(core,request,progress=None):
    validate(request)
    if core.is_admin() or not needs_admin(core,request):return execute_local(core,request,progress)
    if os.name!='nt':return {'ok':False,'code':'WINDOWS_REQUIRED','detail':'Operação disponível no Windows.'}
    key=str(uuid.uuid4());directory=core.DATA_DIR/'elevation';path=directory/(key+'.json')
    save(path,{'id':key,'created_at':time.time(),'sid':user_sid(core),'request':request})
    result_path=directory/(key+'.result.json');events_path=directory/(key+'.events.json')
    if getattr(sys,'frozen',False):exe=sys.executable;args=['--elevated-request',str(path)]
    else:exe=sys.executable;args=[str(Path(__file__).with_name('azor_launcher.py')),'--elevated-request',str(path)]
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[ctypes.POINTER(SHELLEXECUTEINFO)];shell.ShellExecuteExW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    info=SHELLEXECUTEINFO();info.cbSize=ctypes.sizeof(info);info.fMask=0x40
    info.lpVerb='runas';info.lpFile=exe;info.lpParameters=subprocess.list2cmdline(args)
    info.lpDirectory=str(Path(exe).parent);info.nShow=0
    if progress:progress('Permissão do Windows','waiting','Autorize somente esta operação. A interface continua sem privilégios elevados.')
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        code=ctypes.get_last_error()
        return {'ok':False,'code':'UAC_CANCELLED' if code==1223 else 'ELEVATION_FAILED',
                'detail':'A autorização foi cancelada; nenhuma operação foi iniciada.' if code==1223 else 'O Windows não autorizou a operação. Código '+str(code),'results':[]}
    seen=0
    try:
        while True:
            status=kernel.WaitForSingleObject(info.hProcess,250)
            if status not in (0,258):raise OSError('ELEVATED_WORKER_WAIT_FAILED')
            try:
                events=read(events_path)
                for event in events[seen:]:
                    if progress:progress(event['name'],event['status'],event['detail'])
                seen=len(events)
            except (OSError,ValueError):pass
            if status==0:break
        if not result_path.exists():
            return {'ok':False,'code':'ELEVATED_RESULT_MISSING','detail':'A operação terminou sem confirmação. Confira o histórico antes de repetir.','results':[]}
        result=read(result_path)
        if result.get('id')!=key:raise ValueError('ELEVATED_RESULT_INVALID')
        core.invalidate_cache()
        return result['result']
    finally:kernel.CloseHandle(info.hProcess)

def worker_main(request_path):
    import azor_core as core
    path=Path(request_path).resolve();directory=(core.DATA_DIR/'elevation').resolve()
    if path.parent!=directory or not re.fullmatch(r'[a-f0-9-]{36}\.json',path.name):
        raise ValueError('ELEVATION_REQUEST_PATH_INVALID')
    item=read(path);key=path.stem
    result_path=directory/(key+'.result.json')
    if result_path.exists():return
    try:
        if item.get('id')!=key or abs(time.time()-float(item.get('created_at',0)))>600:
            raise ValueError('ELEVATION_REQUEST_EXPIRED')
        if not core.is_admin():raise ValueError('ADMIN_REQUIRED')
        if item.get('sid')!=user_sid(core):raise ValueError('USER_CHANGED: autorize com a mesma conta para preservar os valores do usuário.')
        validate(item['request'])
        import msvcrt
        with (directory/'worker.lock').open('a+b') as stream:
            stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            events=[]
            def progress(name,status,detail):
                events.append({'name':name,'status':status,'detail':detail})
                save(directory/(key+'.events.json'),events)
            try:result=execute_local(core,item['request'],progress)
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
    except Exception as exc:result={'ok':False,'code':'OPERATION_FAILED','detail':str(exc),'results':[]}
    save(result_path,{'id':key,'result':result})
