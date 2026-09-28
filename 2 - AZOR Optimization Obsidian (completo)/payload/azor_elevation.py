"""Elevate only a requested operation; the dashboard remains a standard-user process."""
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

OPERATIONS={'full_optimize','quick_optimize','apply_task','revert_task','revert_tasks','restore_all','restore_transaction','power_plan','power_cpu','service','logon_autoapply'}
def validate(request):
    if not isinstance(request,dict) or request.get('operation') not in OPERATIONS:
        raise ValueError('OPERATION_INVALID')
    profile=request.get('profile','safe')
    if profile not in ('safe','competitive','ultra','auto','campanha','stream','maximo','agressivo'):
        raise ValueError('PROFILE_INVALID')
    if request['operation']=='logon_autoapply' and not isinstance(request.get('enabled'),bool):
        raise ValueError('ENABLED_INVALID')
    if request['operation']=='revert_task' and not re.fullmatch(r'[a-z0-9_]{2,64}',str(request.get('id',''))):
        raise ValueError('TASK_INVALID')
    if request['operation']=='restore_all' and request.get('target','baseline') not in ('baseline','last'):
        raise ValueError('TARGET_INVALID')
    if request['operation']=='revert_tasks':
        ids=request.get('ids')
        if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not re.fullmatch(r'[a-z0-9_]{2,64}',str(i)) for i in ids):
            raise ValueError('TASKS_INVALID')
    return request

def execute_local(core,request,progress=None):
    from azor_modules import engine,transactions
    from azor_managers import PowerManager,ServiceManager
    validate(request);op=request['operation'];profile=request.get('profile','safe')
    if op=='full_optimize':
        report=core.full_optimize(profile,progress)
        # Nos modos da tela inicial o mesmo clique deixa a reaplicacao no login
        # configurada: a elevacao ja foi autorizada para esta operacao.
        if profile in ('maximo','agressivo') and request.get('keep_on_logon') is not False:
            report['logon_autoapply']=_keep_on_logon(core,report,profile,progress)
        return report
    if op=='quick_optimize':
        rows=core.quick_optimize(profile=profile)
        failed=sum(r.get('status') in ('failed','error') for r in rows)
        known={'completed','verified','applied','skipped','preserved','not_applicable','failed','error'}
        unknown=sum(r.get('status') not in known for r in rows)
        changed=sum(r.get('status') in ('completed','verified','applied') and not r.get('already_applied')
                    and r.get('name') not in ('Hardware profile','Backup / Restore') for r in rows)
        ok=False if failed else None if unknown or not rows else True
        return {'ok':ok,'results':rows,
                'detail':f'{changed} alteração(ões) confirmada(s), {failed} falha(s), {unknown} resultado(s) não confirmado(s). Nenhum ganho de FPS foi medido.'}
    if op=='apply_task':return engine.apply_task(str(request.get('id','')),profile)
    if op=='revert_task':return core.revert_optimization(str(request.get('id','')))
    if op=='revert_tasks':
        rows=[core.revert_optimization(str(i)) for i in request['ids']]
        done=sum(1 for r in rows if r.get('ok'))
        return {'ok':done==len(rows),'results':rows,
                'detail':f'{done} de {len(rows)} ajuste(s) desfeito(s) e relido(s).'}
    if op=='restore_all':return core.restore_all_report(str(request.get('target','baseline')))
    if op=='restore_transaction':return transactions.restore(core,str(request.get('id','')))
    if op=='power_plan':return PowerManager(core).apply_plan(str(request.get('guid','')))
    if op=='power_cpu':return PowerManager(core).cpu_policy(str(request.get('guid','')),request.get('minimum'),request.get('maximum'),str(request.get('boost','system')))
    if op=='service':return ServiceManager(core).configure(str(request.get('name','')),str(request.get('start_type','')),request.get('confirmed') is True)
    if op=='logon_autoapply':
        import azor_autostart
        if request['enabled']:return azor_autostart.install(core,profile if profile in azor_autostart.PROFILES else 'maximo',progress)
        return azor_autostart.uninstall(core)

def _keep_on_logon(core,report,profile,progress):
    backup=next((r for r in report.get('results') or [] if r.get('name')=='Backup / Restore'),{})
    if backup.get('status')!='completed':
        return {'ok':False,'detail':'Backup não confirmado: a reaplicação no login não foi configurada.'}
    if not core.is_admin():
        return {'ok':False,'detail':'Esta execução não tinha privilégio de administrador; a reaplicação no login não foi configurada.'}
    import azor_autostart
    try:return azor_autostart.install(core,profile,progress)
    except Exception as exc:return {'ok':False,'detail':str(exc)}

def _task_needs_admin(task):
    """So dispensa o UAC quando o item grava apenas chaves do proprio usuario.

    `requires_admin` sozinho deixava de fora o que grava por powercfg, servico ou
    caminho descoberto na hora (CPU sem repouso, NVMe, interrupcao da GPU): o
    clique rodava sem elevacao e parava em "exige administrador". Desfazer nem
    passava por aqui.
    """
    if task is None:
        return False
    keys=tuple(task.registry_keys or ())
    user_only=bool(keys) and all(str(k[0]).upper()=='HKCU' for k in keys) and not task.power_changes
    return bool(task.requires_admin) or not user_only

def needs_admin(core,request):
    from azor_modules import engine,policy
    op=request['operation']
    if op in ('power_plan','power_cpu','service','logon_autoapply'):return True
    if op=='restore_transaction':
        id=str(request.get('id',''))
        if not re.fullmatch(r'[a-f0-9-]{36}',id):raise ValueError('TRANSACTION_INVALID')
        item=read(core.DATA_DIR/'transactions'/(id+'.json'))
        return item.get('requires_admin') or item['before']['kind']!='registry' or any(e['root']=='HKLM' for e in item['before'].get('entries',[]))
    # Desfazer tudo grava HKLM, plano de energia e paginacao.
    if op=='restore_all':return True
    tasks=engine._all_tasks()
    if op=='revert_tasks':
        by_id={t.id:t for t in tasks}
        return any(_task_needs_admin(by_id.get(i)) for i in request.get('ids') or [])
    if op in ('apply_task','revert_task'):
        task=next((t for t in tasks if t.id==request.get('id')),None)
        if op=='apply_task' and (task is None or task.apply is None):return False
        return _task_needs_admin(task)
    ctx=engine._context(core,request.get('profile','safe'))
    for task in tasks:
        if task.requires_admin and task.apply and task.supports_profile(ctx['resolved_profile']) and policy.automatic_decision(task,ctx)[0]:
            return True
    return False

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
