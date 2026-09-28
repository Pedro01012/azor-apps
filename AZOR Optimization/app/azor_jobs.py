"""Uma operação longa por vez, com progresso real e relatório final gravado.

Toda ação que mexe no Windows (BOOST, instalar apps, limpar, reparar) roda como
um job: a tela recebe o id na hora e acompanha as etapas por polling. Um pedido
repetido com a mesma chave devolve o mesmo job em vez de rodar duas vezes.
"""
import copy
from pathlib import Path
import re
import threading
import time
import uuid
from azor_modules.transactions import save, read


class BusyError(RuntimeError):
    pass


class JobManager:
    def __init__(self, directory, operation_lock=None):
        self.directory = Path(directory)
        self.lock = threading.RLock()
        self.operation_lock = operation_lock or threading.RLock()
        self.jobs = {}
        self.keys = {}
        self.active = None

    def get(self, job_id):
        if not re.fullmatch(r'[a-f0-9-]{36}', str(job_id)):
            raise ValueError('Operação inválida.')
        with self.lock:
            if job_id in self.jobs:
                return copy.deepcopy(self.jobs[job_id])
        record = read(self.directory / (job_id + '.json'))
        if record.get('status') in ('queued', 'running'):
            record['status'] = 'interrupted'
            record['detail'] = 'O AZOR foi fechado antes de terminar. Confira o histórico antes de repetir.'
        return record

    def current(self):
        with self.lock:
            return copy.deepcopy(self.jobs[self.active]) if self.active in self.jobs else None

    def submit(self, name, params, key, run, on_done=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', str(key)):
            raise ValueError('Identificador de requisição inválido.')
        with self.lock:
            if key in self.keys:
                previous = self.get(self.keys[key])
                if previous['name'] != name:
                    raise ValueError('Este identificador pertence a outra operação.')
                return previous
            if self.active:
                raise BusyError('Já existe uma operação em andamento. Aguarde terminar.')
            job_id = str(uuid.uuid4())
            job = {'id': job_id, 'name': name, 'params': params, 'request_key': key, 'status': 'queued',
                   'created_at': time.time(), 'events': [], 'result': None, 'phase': ''}
            save(self.directory / (job_id + '.json'), job)
            self.jobs[job_id] = job
            self.keys[key] = job_id
            self.active = job_id

        def progress(step, status, detail=''):
            with self.lock:
                job['events'].append({'name': str(step), 'status': str(status), 'detail': str(detail or ''),
                                      'time': time.time()})
                job['events'] = job['events'][-400:]
                job['status'] = 'running'
                job['phase'] = str(step)

        def work():
            try:
                with self.operation_lock:
                    result = run(progress)
                with self.lock:
                    job['result'] = result
                    job['status'] = 'completed' if isinstance(result, dict) and result.get('ok') is True else 'failed'
                if on_done:
                    try:
                        on_done(result)
                    except Exception:
                        pass
            except Exception as exc:
                with self.lock:
                    job['status'] = 'failed'
                    job['detail'] = str(exc)
            finally:
                with self.lock:
                    job['finished_at'] = time.time()
                    try:
                        save(self.directory / (job_id + '.json'), job)
                    except Exception as exc:
                        job['status'] = 'failed'
                        job['detail'] = 'Registro final não confirmado: ' + str(exc)
                    self.active = None

        threading.Thread(target=work, name='azor-job-' + name, daemon=False).start()
        return self.get(job_id)
