"""Shared Windows managers. Inject the existing core; never duplicate low-level writers."""
from __future__ import annotations
import os
from pathlib import Path
import re
import sys
from azor_modules.base import OptimizationTask
from azor_modules import transactions

class WindowsDetection:
    @staticmethod
    def read():
        if os.name!='nt':return {'supported':False,'build':None,'reason':'Windows necessário.'}
        v=sys.getwindowsversion()
        return {'supported':v.major==10 and v.build>=19041 and sys.maxsize>2**32,'build':v.build,
                'name':'Windows 11' if v.build>=22000 else 'Windows 10',
                'architecture':'64-bit' if sys.maxsize>2**32 else '32-bit',
                'reason':'Windows 10/11, build 19041 ou posterior.'}

class RegistryManager:
    def __init__(self,core):self.core=core
    def read(self,root,path,name):
        value=self.core.reg_read(root,path,name)
        if not isinstance(value,dict) or type(value.get('exists')) is not bool:
            raise ValueError('REGISTRY_READ_UNCONFIRMED: valor original não confirmado.')
        if value['exists'] and ('value' not in value or type(value.get('type')) is not int):
            raise ValueError('REGISTRY_TYPE_UNCONFIRMED: tipo original não confirmado.')
        return value
    def backup(self,keys):
        return [dict(root=r,path=p,name=n,**self.read(r,p,n)) for r,p,n in keys]
    def restore(self,entries):
        for e in reversed(entries):
            if e['exists']:self.core.reg_write(e['root'],e['path'],e['name'],e['value'],e['type'])
            else:self.core.reg_delete_value(e['root'],e['path'],e['name'])
            got=self.read(e['root'],e['path'],e['name'])
            if got['exists']!=e['exists'] or (e['exists'] and (got['value']!=e['value'] or got['type']!=e['type'])):
                raise ValueError('REGISTRY_RESTORE_UNCONFIRMED: releitura diferente do original.')
        return True

class PowerManager:
    BOOST={'system':None,'disabled':0,'performance':1,'aggressive':2,'efficiency':3,'efficient_aggressive':4}
    def __init__(self,core):self.core=core
    def plans(self):
        rows=self.core.list_power_schemes()
        return {'ok':True,'plans':rows,'active':self.core.get_active_power_scheme(),
                'azor':self.core.azor_fps_boost_power_status()}
    def _guid(self,guid):
        if not re.fullmatch(r'[a-fA-F0-9-]{36}',str(guid)):raise ValueError('POWER_INVALID_SCHEME')
        if not any(str(r.get('guid','')).lower()==guid.lower() for r in self.core.list_power_schemes()):
            raise ValueError('POWER_SCHEME_NOT_FOUND')
        return guid.lower()
    def apply_plan(self,guid,on_prepared=None):
        guid=self._guid(guid)
        def apply(c,ctx):
            p=c.run_hidden(['powercfg','/setactive',guid],timeout=15)
            return p.returncode==0,'Plano solicitado.' if p.returncode==0 else 'POWER_SCHEME_ACCESS_DENIED: '+str(p.stderr or p.stdout)
        task=OptimizationTask(id='power_plan',name='Trocar plano de energia',module='power',category='Energia',
            profiles=('safe',),requires_admin=True,apply=apply,verify=lambda c,x:(str(c.get_active_power_scheme()).lower()==guid,'Plano ativo relido.'))
        return transactions.run(self.core,task,{'resolved_profile':'safe','on_prepared':on_prepared})
    def cpu_state(self,guid=None):
        guid=self._guid(guid or self.core.get_active_power_scheme())
        values={name:self.core._powercfg_index_for_scheme(guid,'SUB_PROCESSOR',setting,'ac')
                for name,setting in [('minimum','PROCTHROTTLEMIN'),('maximum','PROCTHROTTLEMAX'),('boost','PERFBOOSTMODE')]}
        return {'ok':True,'guid':guid,**values,'boost_options':self.BOOST,
                'note':'Opções AC. Sistema preserva a política atual; suporte real depende do processador e driver.'}
    def cpu_policy(self,guid,minimum=None,maximum=None,boost='system'):
        guid=self._guid(guid)
        if boost not in self.BOOST:raise ValueError('POWER_INVALID_BOOST')
        changes=[]
        for setting,value in [('PROCTHROTTLEMIN',minimum),('PROCTHROTTLEMAX',maximum),('PERFBOOSTMODE',self.BOOST[boost])]:
            if value is None:continue
            if type(value) is not int or not 0<=value<=100:raise ValueError('POWER_INVALID_CPU_LIMIT')
            before=self.core._powercfg_index_for_scheme(guid,'SUB_PROCESSOR',setting,'ac')
            if before is None:raise ValueError('POWER_SETTING_UNSUPPORTED: '+setting)
            changes.append((guid,'SUB_PROCESSOR',setting,'ac',value))
        current=self.cpu_state(guid)
        low=minimum if minimum is not None else current['minimum']
        high=maximum if maximum is not None else current['maximum']
        if low is None or high is None:raise ValueError('POWER_CPU_LIMITS_UNAVAILABLE')
        if low>high:
            raise ValueError('O mínimo não pode exceder o máximo.')
        if not changes:return {'ok':True,'detail':'Política do sistema preservada; nenhuma alteração.'}
        def apply(c,ctx):
            for g,sub,key,mode,value in changes:
                ok,detail=c._set_powercfg_value_verified(g,sub,key,value,key,mode)
                if not ok:return False,detail
            if c.get_active_power_scheme()==guid:
                p=c.run_hidden(['powercfg','/setactive',guid],timeout=10)
                if p.returncode:return False,'POWER_REFRESH_FAILED'
            return True,'Política de CPU aplicada.'
        def verify(c,ctx):
            ok=all(c._powercfg_index_for_scheme(g,sub,key,mode)==value for g,sub,key,mode,value in changes)
            return ok,'Política relida.' if ok else 'POWER_VERIFY_FAILED'
        task=OptimizationTask(id='power_cpu_policy',name='Política de CPU',module='power',category='Energia',
            profiles=('safe',),apply=apply,verify=verify,power_changes=tuple(changes))
        return transactions.run(self.core,task,{'resolved_profile':'safe'})

class ServiceManager:
    PROTECTED=frozenset('rpcss dcomlaunch eventlog plugplay power schedule bfe mpssvc windefend sense wscsvc securityhealthservice wuauserv bits cryptsvc trustedinstaller appxsvc clipsvc audiosrv audioendpointbuilder hidserv vgk vgc easyanticheat easyanticheat_eos beservice'.split())
    OPTIONAL=frozenset(('diagtrack','spooler','xblgamesave','xboxnetapisvc','xboxgipsvc','bthserv'))
    def __init__(self,core):self.core=core
    def state(self,name):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',str(name)):raise ValueError('SERVICE_INVALID_NAME')
        config=self.core.service_state(name)
        if not config.get('exists'):return config
        running=self.core.powershell_json("$s=Get-Service -Name '"+name+"' -ErrorAction Stop; [pscustomobject]@{State=[int]$s.Status;Dependents=@($s.DependentServices|Where-Object {$_.Status -eq 'Running'}|Select-Object -ExpandProperty Name)}",timeout=15)
        if not isinstance(running,dict) or running.get('State') not in (1,4):raise ValueError('SERVICE_STATE_UNCONFIRMED')
        return {**config,'running':running['State']==4,'runtime_state':running['State'],'dependents':running.get('Dependents') or []}
    def can_disable(self,name):
        low=str(name).lower()
        if low in self.PROTECTED or low not in self.OPTIONAL:
            return False,'Serviço protegido ou não classificado. Nenhuma alteração permitida.'
        state=self.state(name)
        if not state.get('exists'):return False,'Serviço não encontrado.'
        if state.get('dependents'):return False,'Há serviços dependentes ativos.'
        return True,'Requer confirmação de que o recurso não é usado, inclusive periféricos e Game Pass.'
    def configure(self,name,start_type,confirmed=False):
        if str(name).lower() not in self.OPTIONAL:
            return {'ok':False,'detail':'Serviço protegido ou não classificado; nenhuma alteração permitida.'}
        if start_type not in ('Automatic','Manual','Disabled'):raise ValueError('SERVICE_INVALID_START_TYPE')
        if start_type=='Disabled':
            ok,detail=self.can_disable(name)
            if not ok or not confirmed:return {'ok':False,'detail':detail}
        elif str(name).lower() in self.PROTECTED:
            return {'ok':False,'detail':'Serviço protegido; use o reparo específico do Windows.'}
        self.state(name)
        key=('HKLM','SYSTEM\\CurrentControlSet\\Services\\'+name,'Start')
        target=self.core.SERVICE_START_TYPES[start_type]
        def verify(c,ctx):
            state=self.state(name)
            ok=state.get('start')==target and (target!=4 or not state['running'])
            return ok,'Estado do serviço relido.' if ok else 'SERVICE_VERIFY_FAILED'
        task=OptimizationTask(id='service_'+name.casefold(),name='Serviço '+name,module='services',category='Serviços',
            profiles=('safe',),requires_admin=True,apply=lambda c,x:c.set_service_start_verified(name,start_type),verify=verify,registry_keys=(key,))
        return transactions.run(self.core,task,{'resolved_profile':'safe'})

class HardwareDetection:
    def __init__(self,core):self.core=core
    def read(self):
        return {'windows':WindowsDetection.read(),'hardware':self.core.hardware_profile(),
                'memory':self.core._memory_windows(),'power':self.core.get_active_power_scheme()}
