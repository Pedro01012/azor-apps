"""Durable before-images and verified rollback; no Windows changes on import."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import re
import time
import threading
import uuid
from .base import normalize_result
from .power_policy import POWER_SETTINGS

_ORDER_LOCK=threading.Lock()

def _order(record):
    # Persist order separately from display time. Legacy records retain their timestamp.
    return int(record.get('order_ns') or int((record.get('time') or 0)*1_000_000_000))

def _encode(value):
    if isinstance(value,bytes): return {'$binary':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict): return {k:_encode(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [_encode(v) for v in value]
    return value

def _decode(value):
    if isinstance(value,dict):
        if set(value)=={'$binary'}:return base64.b64decode(value['$binary'],validate=True)
        return {k:_decode(v) for k,v in value.items()}
    if isinstance(value,list):return [_decode(v) for v in value]
    return value

def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8') as stream:
        json.dump(_encode(value),stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
    if read(path)!=value:raise IOError('O registro da transação não pôde ser relido.')

def read(path):
    return _decode(json.loads(Path(path).read_text(encoding='utf-8')))

def supported(task):
    return bool(task.registry_keys or task.power_changes) or task.id in ('power_plan','automatic_pagefile','usb_suspend_off')

def capture(core,task):
    if task.power_changes:
        values=[]
        for guid,subgroup,setting,mode,target in task.power_changes:
            original=core._powercfg_index_for_scheme(guid,subgroup,setting,mode)
            if type(original) is not int:raise ValueError('POWER_SNAPSHOT_UNCONFIRMED')
            values.append([guid,subgroup,setting,mode,original])
        return {'kind':'power_settings','values':values}
    if task.registry_keys:
        from azor_managers import RegistryManager
        rows=RegistryManager(core).backup(task.registry_keys)
        snap={'kind':'registry','entries':rows}
        if task.module=='services':
            service=rows[0]['path'].split('\\')[-1]
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',service):raise ValueError('Serviço inválido.')
            state=core.powershell_json("$s=Get-Service -Name '"+service+"' -ErrorAction Stop; [pscustomobject]@{State=[int]$s.Status;Dependents=@($s.DependentServices|Where-Object {$_.Status -eq 'Running'}|Select-Object -ExpandProperty Name)}",timeout=15)
            if not isinstance(state,dict) or state.get('State') not in (1,4):raise ValueError('Estado do serviço não confirmado.')
            if state.get('Dependents'):raise ValueError('Há serviços dependentes ativos. Alteração bloqueada.')
            snap['service']={'name':service,'state':state['State']}
        return snap
    if task.id=='automatic_pagefile':
        value=core.get_automatic_pagefile()
        if not isinstance(value,bool):raise ValueError('Paginação anterior não confirmada.')
        return {'kind':'pagefile','value':value}
    if task.id=='usb_suspend_off':
        value=core.get_usb_selective_suspend_state()
        guid=core.get_active_power_scheme()
        if not isinstance(value,dict) or any(value.get(k) not in (0,1) for k in ('ac','dc')) or not guid:
            raise ValueError('Estado USB/plano anterior não confirmado.')
        return {'kind':'usb','value':value,'guid':guid}
    if task.id=='power_plan':
        guid=core.get_active_power_scheme()
        if not isinstance(guid,str) or not re.fullmatch(r'[0-9a-fA-F-]{36}',guid):raise ValueError('Plano original não confirmado.')
        owned=core._scheme_by_profile('azor_fps_boost') or {}
        values=[]
        values_guid=str(owned.get('guid') or guid)
        if owned.get('guid'):
            for key,subgroup,setting,target,label in POWER_SETTINGS:
                value=core._powercfg_index_for_scheme(values_guid,subgroup,setting,'ac')
                if value is not None:values.append([subgroup,setting,value])
        return {'kind':'power','guid':guid,'values':values,'values_guid':values_guid}
    raise ValueError('Este ajuste ainda não tem captura transacional do estado anterior. Nenhuma alteração iniciada.')

def undo(core,snap):
    errors=[]
    kind=snap.get('kind')
    if kind=='registry':
        service=snap.get('service')
        for entry in reversed(snap['entries']):
            try:
                root,path,name=entry['root'],entry['path'],entry['name']
                # Já está como antes: nada a gravar. Chave que o Windows protege
                # contra escrita (TaskbarDa no Windows 11 atual) reprovava o desfazer
                # mesmo sem ter mudado.
                now=core.reg_read(root,path,name)
                if now.get('exists')==entry['exists'] and (not entry['exists'] or (
                        now.get('type')==entry['type'] and now.get('value')==entry['value'])):
                    continue
                if service and name=='Start':
                    ok,detail=core.set_service_start_verified(service['name'],core.SERVICE_START_NAMES[entry['value']])
                    if not ok:raise ValueError(detail)
                elif entry['exists']:core.reg_write(root,path,name,entry['value'],entry['type'])
                else:core.reg_delete_value(root,path,name)
                got=core.reg_read(root,path,name)
                if got.get('exists')!=entry['exists'] or (entry['exists'] and (got.get('type')!=entry['type'] or got.get('value')!=entry['value'])):
                    raise ValueError('Releitura não corresponde ao original.')
            except Exception as exc:errors.append(str(exc))
        if service and not errors:
            name=service['name'];verb='Start' if service['state']==4 else 'Stop';expected='Running' if service['state']==4 else 'Stopped'
            state=core.powershell_json("$s=Get-Service -Name '"+name+"' -ErrorAction Stop; "+verb+"-Service -InputObject $s -ErrorAction Stop; $s.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::"+expected+",[TimeSpan]::FromSeconds(10)); $s.Refresh(); [int]$s.Status",timeout=15)
            if state!=service['state']:errors.append('Estado de execução do serviço não restaurado.')
        core._broadcast_setting('Control Panel\\Mouse')
    elif kind=='pagefile':
        ok,detail=core.set_automatic_pagefile_verified(snap['value'])
        if not ok or core.get_automatic_pagefile() is not snap['value']:errors.append(detail)
    elif kind=='power_settings':
        for guid,subgroup,setting,mode,value in snap['values']:
            ok,detail=core._set_powercfg_value_verified(guid,subgroup,setting,value,'Restaurar CPU',mode)
            if not ok:errors.append(detail)
        active=core.get_active_power_scheme()
        if active in {row[0] for row in snap['values']}:
            p=core.run_hidden(['powercfg','/setactive',active],timeout=10)
            if p.returncode:errors.append('POWER_REFRESH_FAILED')
    elif kind in ('power','usb'):
        guid=snap['guid']
        if kind=='power':
            for subgroup,setting,value in snap['values']:
                ok,detail=core._set_powercfg_value_verified(snap.get('values_guid',guid),subgroup,setting,value,'Restaurar energia','ac')
                if not ok:errors.append(detail)
        else:
            for mode in ('ac','dc'):
                # GUIDs: o apelido SUB_USB nao existe no powercfg e o desfazer falhava sempre.
                ok,detail=core._set_powercfg_value_verified(guid,core.USB_SUBGROUP_GUID,core.USB_SELECTIVE_SUSPEND_GUID,snap['value'][mode],'Restaurar USB',mode)
                if not ok:errors.append(detail)
        if kind=='power':
            result=core.run_hidden(['powercfg','/setactive',guid],timeout=10)
            if result.returncode!=0 or str(core.get_active_power_scheme()).lower()!=guid.lower():errors.append('Plano anterior não confirmado.')
    else:raise ValueError('Tipo de snapshot não suportado.')
    return not errors, '; '.join(errors) if errors else 'Estado imediatamente anterior restaurado e relido.'

def run(core,task,ctx):
    if task.verify is None:return {'ok':False,'detail':'Ação sem verificação: não iniciada.'}
    snap=capture(core,task)
    transaction_id=str(uuid.uuid4())
    path=Path(core.DATA_DIR)/'transactions'/(transaction_id+'.json')
    record={'version':1,'id':transaction_id,'task_id':task.id,'name':task.name,'profile':ctx['resolved_profile'],
            'time':time.time(),'status':'prepared','before':snap,'restart':bool(task.restart),
            'category':task.category,'risk':task.risk,'requires_admin':task.requires_admin,
            'classification':task.classification}
    with _ORDER_LOCK:
        record['order_ns']=max(time.time_ns(),max((_order(row)+1 for row in history(core)),default=0))
        save(path,record)
    try:
        if ctx.get('on_prepared'):ctx['on_prepared'](transaction_id)
        ok,detail=normalize_result(task.apply(core,ctx))
        if ok:
            ok,verified=normalize_result(task.verify(core,ctx))
            detail=verified or detail
        if ok:record['after']=capture(core,task)
    except Exception as exc:ok,detail=False,str(exc)
    rollback=None
    if not ok:
        try:
            restored,r_detail=undo(core,snap)
            rollback={'ok':restored,'detail':r_detail}
        except Exception as exc:rollback={'ok':False,'detail':str(exc)}
    record.update(status='applied' if ok else 'rolled_back' if rollback['ok'] else 'recovery_required',
                  detail=detail,rollback=rollback,finished_at=time.time())
    try:save(path,record)
    except Exception as exc:
        # The prepared record remains recoverable even when final log persistence fails.
        if ok:
            try:
                restored,r_detail=undo(core,snap);rollback={'ok':restored,'detail':r_detail}
            except Exception as undo_exc:rollback={'ok':False,'detail':str(undo_exc)}
        ok=False;detail=f'Registro final não confirmado: {exc}'
    return {'ok':ok,'detail':detail,'transaction_id':transaction_id,'rollback':rollback}

def history(core):
    rows=[]
    for path in (Path(core.DATA_DIR)/'transactions').glob('*.json'):
        try:
            item=read(path)
            rows.append({k:item.get(k) for k in ('id','task_id','name','time','order_ns','status','detail','profile','restart')})
        except Exception:rows.append({'id':path.stem,'status':'unreadable','detail':'Registro inválido; preservado para inspeção.'})
    return sorted(rows,key=_order,reverse=True)

def restore(core,transaction_id):
    if not re.fullmatch(r'[0-9a-f-]{36}',str(transaction_id)):raise ValueError('Transação inválida.')
    path=Path(core.DATA_DIR)/'transactions'/(transaction_id+'.json');record=read(path)
    if record.get('status') in ('rolled_back','restored'):return {'ok':True,'detail':'Esta transação já foi restaurada.'}
    def resources(snapshot):
        if snapshot.get('kind') in ('power','usb','power_settings'):return {'power-scheme'}
        if snapshot.get('kind')=='pagefile':return {'pagefile'}
        return {str((e['root'],e['path'],e['name'])).casefold() for e in snapshot.get('entries',[])}
    touched=resources(record['before'])
    newer=[]
    for row in history(core):
        if row['id']!=transaction_id and _order(row)>=_order(record) and row['status'] in ('applied','prepared','recovery_required'):
            other=read(path.with_name(row['id']+'.json'))
            if touched & resources(other['before']):newer.append(row)
    if newer:raise ValueError('Restaure primeiro a alteração mais recente que usa a mesma configuração.')
    ok,detail=undo(core,record['before'])
    record.update(status='restored' if ok else 'recovery_required',detail=detail)
    save(path,record)
    if ok:core.unmark_task_applied(record['task_id'])
    return {'ok':ok,'detail':detail,'restart':bool(record.get('restart'))}
