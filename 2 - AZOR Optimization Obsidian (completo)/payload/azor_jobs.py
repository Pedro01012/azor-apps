"""One active operation, idempotent start, real progress, durable final report."""
import copy
from pathlib import Path
import re
import threading
import time
import uuid
from azor_modules.transactions import save,read

class BusyError(RuntimeError):pass

class JobManager:
    def __init__(self,directory,operation_lock=None):
        self.directory=Path(directory);self.lock=threading.RLock()
        self.operation_lock=operation_lock or threading.RLock()
        self.jobs={};self.keys={};self.active=None

    def get(self,job_id):
        if not re.fullmatch(r'[a-f0-9-]{36}',str(job_id)):raise ValueError('Operação inválida.')
        with self.lock:
            if job_id in self.jobs:return copy.deepcopy(self.jobs[job_id])
        record=read(self.directory/(job_id+'.json'))
        if record.get('status') in ('queued','running'):
            record['status']='interrupted';record['detail']='A sessão anterior terminou sem confirmação. Confira as transações antes de repetir.'
        return record

    def submit(self,name,profile,key,run):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',str(key)):raise ValueError('Identificador de requisição inválido.')
        with self.lock:
            if key in self.keys:
                previous=self.get(self.keys[key])
                if previous['name']!=name or previous['profile']!=profile:raise ValueError('Este identificador pertence a outro perfil.')
                return previous
            # Persisted idempotency survives a browser/server restart.
            for path in self.directory.glob('*.json'):
                try:
                    previous=read(path)
                except (OSError,ValueError):continue
                if previous.get('request_key')==key:
                    if previous['name']!=name or previous['profile']!=profile:raise ValueError('Este identificador pertence a outro perfil.')
                    self.keys[key]=previous['id'];return self.get(previous['id'])
            if self.active:raise BusyError('Já existe uma operação em andamento. Aguarde a conclusão.')
            job_id=str(uuid.uuid4())
            job={'id':job_id,'name':name,'profile':profile,'request_key':key,'status':'queued',
                 'created_at':time.time(),'events':[],'result':None}
            save(self.directory/(job_id+'.json'),job)
            self.jobs[job_id]=job;self.keys[key]=job_id;self.active=job_id
        def progress(name,status,detail):
            with self.lock:
                job['events'].append({'name':name,'status':status,'detail':detail,'time':time.time()})
                job['events']=job['events'][-400:]
                job['status']='running';job['phase']=name
        def work():
            try:
                with self.operation_lock:
                    result=run(progress)
                with self.lock:
                    job['result']=result;job['status']='completed' if result.get('ok') is True else 'failed'
            except Exception as exc:
                with self.lock:job['status']='failed';job['detail']=str(exc)
            finally:
                with self.lock:
                    job['finished_at']=time.time()
                    try:save(self.directory/(job_id+'.json'),job)
                    except Exception as exc:job['status']='failed';job['detail']='Registro final não confirmado: '+str(exc)
                    self.active=None
        threading.Thread(target=work,name='azor-operation',daemon=False).start()
        return self.get(job_id)
