"""Reaplica o modo de desempenho escolhido toda vez que o usuário entra no Windows.

Uma tarefa agendada roda o AZOR sem janela, com o privilégio mais alto da conta,
alguns segundos depois do login, e passa pelo mesmo lote do BOOST: releitura
antes de escrever, backup e reversão. O que já está no lugar não é gravado de novo.

A tarefa roda elevada, então o executável não pode ficar numa pasta que o usuário
comum altera (Downloads, Área de Trabalho). Se ficasse, qualquer programa sem
privilégio trocaria um arquivo ali e ganharia administrador no próximo login. Por
isso a instalação copia o AZOR para Program Files, onde só administrador grava, e
a tarefa aponta para essa cópia. O XML da tarefa também é escrito lá, e não na
pasta temporária do usuário, pelo mesmo motivo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = 'AZOR Optimization - Desempenho no login'
PROFILES = ('maximo', 'agressivo')
LOGON_DELAY = 'PT45S'
STATUS_NAME = 'logon_autoapply.json'
MANIFEST_NAME = 'azor-install.json'
TASK_XML_NAME = 'azor-logon-task.xml'
FROZEN_EXE_NAME = 'AZOR Optimization.exe'
PAYLOAD_IGNORE = ('__pycache__', '*.pyc', 'data', 'web', 'docs')


def install_root() -> Path:
    base = os.environ.get('ProgramW6432') or os.environ.get('ProgramFiles') or r'C:\Program Files'
    return Path(base) / 'AZOR Optimization' / 'logon'


# ------------------------------------------------------------------ estado local
def _status_path(core) -> Path:
    return Path(core.DATA_DIR) / STATUS_NAME


def read_status(core) -> dict:
    try:
        data = json.loads(_status_path(core).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def _write_status(core, **fields) -> dict:
    data = read_status(core)
    data.update(fields)
    _write_json(_status_path(core), data)
    return data


# ------------------------------------------------------------------ cópia protegida
def source_layout() -> dict:
    if getattr(sys, 'frozen', False):
        return {'kind': 'frozen', 'exe': Path(sys.executable).resolve()}
    payload = Path(__file__).resolve().parent
    runtime = payload.parent / 'runtime'
    if not (runtime / 'pythonw.exe').is_file():
        raise RuntimeError('o pacote completo do AZOR (pasta runtime ao lado de payload) é necessário '
                           'para a aplicação automática no login')
    return {'kind': 'portable', 'payload': payload, 'runtime': runtime}


def _skip_payload(relative: Path) -> bool:
    parts = relative.parts
    return (not parts or parts[0] in ('data', 'web', 'docs') or '__pycache__' in parts
            or relative.suffix == '.pyc')


def fingerprint(layout: dict) -> str:
    """Muda quando o código muda; decide se a cópia em Program Files precisa ser refeita."""
    digest = hashlib.sha256(layout['kind'].encode('ascii'))
    if layout['kind'] == 'frozen':
        stat = layout['exe'].stat()
        digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode('ascii'))
        return digest.hexdigest()
    for path in sorted(layout['payload'].rglob('*')):
        relative = path.relative_to(layout['payload'])
        if path.is_file() and not _skip_payload(relative):
            digest.update(relative.as_posix().encode('utf-8'))
            digest.update(path.read_bytes())
    for path in sorted(layout['runtime'].rglob('*')):
        if path.is_file():
            stat = path.stat()
            name = path.relative_to(layout['runtime']).as_posix()
            digest.update(f'{name}:{stat.st_size}:{stat.st_mtime_ns}'.encode('utf-8'))
    return digest.hexdigest()


def task_command(root: Path, kind: str):
    if kind == 'frozen':
        return str(root / FROZEN_EXE_NAME), '--logon-apply', str(root)
    launcher = root / 'payload' / 'azor_launcher.py'
    return str(root / 'runtime' / 'pythonw.exe'), f'"{launcher}" --logon-apply', str(root / 'payload')


def _read_manifest(root: Path) -> dict:
    try:
        data = json.loads((root / MANIFEST_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _copy_to(root: Path, layout: dict) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = root.with_name(root.name + '.novo-' + uuid.uuid4().hex[:8])
    try:
        staging.mkdir()
        if layout['kind'] == 'frozen':
            shutil.copy2(layout['exe'], staging / FROZEN_EXE_NAME)
        else:
            shutil.copytree(layout['payload'], staging / 'payload', ignore=shutil.ignore_patterns(*PAYLOAD_IGNORE))
            shutil.copytree(layout['runtime'], staging / 'runtime', ignore=shutil.ignore_patterns('__pycache__'))
        if root.exists():
            if not (root / MANIFEST_NAME).exists():
                raise RuntimeError(f'{root} já existe e não foi criado pelo AZOR; nada foi substituído')
            retired = root.with_name(root.name + '.antigo-' + uuid.uuid4().hex[:8])
            os.replace(root, retired)
            shutil.rmtree(retired, ignore_errors=True)
        os.replace(staging, root)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


# ------------------------------------------------------------------ tarefa do Windows
def task_xml(sid: str, command: str, arguments: str, workdir: str) -> str:
    if not re.fullmatch(r'S-1-[0-9]+(?:-[0-9]+)+', str(sid or '')):
        raise ValueError('USER_SID_INVALID')
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>AZOR Optimization</Author>
    <Description>Reaplica o modo de desempenho escolhido no AZOR ao entrar no Windows. Para desligar: AZOR &gt; Ajustes &gt; Manter no máximo ao entrar no Windows.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{sid}</UserId>
      <Delay>{LOGON_DELAY}</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{sid}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''


def _schtasks(core, *args, timeout=30):
    return core.run_hidden(['schtasks', *args], timeout=timeout)


def _output(result) -> str:
    return ((result.stderr or '') + (result.stdout or '')).replace('\x00', '').strip()


def query_task(core) -> dict:
    if os.name != 'nt':
        return {'exists': False}
    try:
        result = _schtasks(core, '/Query', '/TN', TASK_NAME, '/XML', timeout=15)
    except Exception as exc:
        return {'exists': False, 'error': str(exc)}
    if result.returncode != 0:
        return {'exists': False}
    xml = (result.stdout or '').replace('\x00', '')
    match = re.search(r'<Command>(.*?)</Command>', xml, re.S)
    command = (match.group(1).strip() if match else '').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return {'exists': True, 'command': command,
            'enabled': '<Enabled>false</Enabled>' not in xml,
            'highest': '<RunLevel>HighestAvailable</RunLevel>' in xml,
            'on_battery': '<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>' in xml}


def install(core, profile: str = 'maximo', progress=None) -> dict:
    if profile not in PROFILES:
        raise ValueError('PROFILE_INVALID')
    if os.name != 'nt':
        return {'ok': False, 'enabled': False, 'detail': 'Disponível apenas no Windows.'}
    if not core.is_admin():
        return {'ok': False, 'enabled': False,
                'detail': 'Ligar a aplicação no login exige autorização de administrador.'}
    if progress:
        progress('Aplicação automática no login', 'applying',
                 'Guardando uma cópia protegida do AZOR em Program Files e registrando a tarefa do Windows.')
    root = install_root()
    try:
        layout = source_layout()
        digest = fingerprint(layout)
        command, arguments, workdir = task_command(root, layout['kind'])
        if _read_manifest(root).get('fingerprint') != digest or not Path(command).is_file():
            _copy_to(root, layout)
            _write_json(root / MANIFEST_NAME, {'fingerprint': digest, 'kind': layout['kind'], 'copied_at': time.time()})
        from azor_elevation import user_sid
        xml_path = root / TASK_XML_NAME
        xml_path.write_text(task_xml(user_sid(core), command, arguments, workdir), encoding='utf-16')
        created = _schtasks(core, '/Create', '/TN', TASK_NAME, '/XML', str(xml_path), '/F')
        if created.returncode != 0:
            raise RuntimeError(_output(created) or f'schtasks terminou com código {created.returncode}')
        task = query_task(core)
        ok = bool(task.get('exists') and task.get('highest')
                  and str(task.get('command') or '').casefold() == command.casefold())
    except Exception as exc:
        core.journal('logon_autoapply_install_failed', error=str(exc))
        return {'ok': False, 'enabled': False, 'detail': f'A tarefa do Windows não foi configurada: {exc}'}
    label = 'Agressivo' if profile == 'agressivo' else 'Máximo'
    detail = (f'O AZOR vai reaplicar o modo {label} toda vez que você entrar no Windows, também na bateria.'
              if ok else 'A tarefa foi enviada ao Windows, mas a releitura não confirmou o comando esperado.')
    _write_status(core, enabled=ok, profile=profile, installed_at=time.time() if ok else None,
                  install_root=str(root), detail=detail)
    core.journal('logon_autoapply_installed', ok=ok, profile=profile, root=str(root))
    return {'ok': ok, 'enabled': ok, 'profile': profile, 'detail': detail}


def uninstall(core) -> dict:
    if os.name != 'nt':
        return {'ok': False, 'enabled': False, 'detail': 'Disponível apenas no Windows.'}
    if not core.is_admin():
        return {'ok': False, 'detail': 'Desligar a aplicação no login exige autorização de administrador.'}
    if query_task(core).get('exists'):
        deleted = _schtasks(core, '/Delete', '/TN', TASK_NAME, '/F')
        if deleted.returncode != 0 or query_task(core).get('exists'):
            return {'ok': False, 'enabled': True,
                    'detail': 'O Windows não removeu a tarefa: ' + (_output(deleted) or 'sem detalhe')}
    root = install_root()
    copy_removed = True
    # Só apaga a pasta que o próprio AZOR criou (tem o manifesto dele).
    if root.exists() and (root / MANIFEST_NAME).exists():
        shutil.rmtree(root, ignore_errors=True)
        copy_removed = not root.exists()
        try:
            root.parent.rmdir()
        except OSError:
            pass
    detail = 'O AZOR não vai mais reaplicar ajustes ao entrar no Windows.'
    if not copy_removed:
        detail += ' A cópia em Program Files não pôde ser apagada agora, mas não roda mais sozinha.'
    _write_status(core, enabled=False, removed_at=time.time(), detail=detail)
    core.journal('logon_autoapply_removed', copy_removed=copy_removed)
    return {'ok': True, 'enabled': False, 'detail': detail}


def installed_copy_is_current():
    """True/False quando a cópia de Program Files pode ser comparada com este pacote; None quando não."""
    try:
        recorded = _read_manifest(install_root()).get('fingerprint')
        return None if not recorded else recorded == fingerprint(source_layout())
    except Exception:
        return None


def status(core, query: bool = True) -> dict:
    data = read_status(core)
    out = {'enabled': bool(data.get('enabled')), 'profile': data.get('profile'),
           'installed_at': data.get('installed_at'), 'last_run': data.get('last_run'),
           'detail': data.get('detail'), 'stale': False}
    # A tarefa só é consultada quando o AZOR acha que está ligada: consultar custa um processo.
    if query and out['enabled'] and os.name == 'nt' and not query_task(core).get('exists'):
        out.update(enabled=False,
                   detail='A tarefa não está mais registrada no Windows. Rode o BOOST para configurar de novo.')
    # A cópia só é refeita pelo BOOST. Quem extrai uma versão nova e não aperta BOOST
    # continuava com o login rodando o código antigo, sem aviso nenhum.
    if out['enabled'] and installed_copy_is_current() is False:
        out.update(stale=True,
                   detail='O login ainda usa a cópia de outra versão do AZOR. Aperte BOOST uma vez nesta versão '
                          'para o login passar a usar esta.')
    return out


# ------------------------------------------------------------------ execução no login
def run_logon() -> int:
    import azor_core as core
    started = time.time()

    def finish(outcome, **fields):
        _write_status(core, last_run={'time': started, 'finished': time.time(), 'outcome': outcome, **fields})
        core.journal('logon_autoapply_run', outcome=outcome, **fields)
        return 0 if outcome in ('applied', 'skipped') else 1

    status_now = read_status(core)
    if not status_now.get('enabled'):
        return finish('skipped', detail='Aplicação automática desligada no AZOR.')
    if not core.is_admin():
        return finish('failed', detail='A tarefa rodou sem privilégio de administrador; nada foi alterado.')
    profile = str(core.load_settings().get('performance_mode') or status_now.get('profile') or 'maximo')
    if profile not in PROFILES:
        profile = 'maximo'
    import msvcrt
    lock_dir = Path(core.DATA_DIR) / 'elevation'
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / 'worker.lock').open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return finish('skipped', profile=profile, detail='Outra otimização do AZOR estava em andamento.')
        try:
            from azor_modules import engine
            results = engine.execute(profile)
        except Exception as exc:
            return finish('failed', profile=profile, detail=f'O lote não pôde rodar: {exc}')
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    tweaks = [r for r in results if r.get('id')]
    changed = sum(r.get('status') == 'completed' and not r.get('already_applied') for r in tweaks)
    already = sum(r.get('status') == 'completed' and bool(r.get('already_applied')) for r in tweaks)
    failed_items = [{'name': str(r.get('name') or r.get('id') or 'ajuste'), 'detail': str(r.get('detail') or '')}
                    for r in results if r.get('status') == 'failed']
    failed = len(failed_items)
    backup_ok = any(r.get('name') == 'Backup / Restore' and r.get('status') == 'completed' for r in results)
    outcome = 'applied' if backup_ok and not failed else 'partial' if backup_ok else 'failed'
    detail = f'{changed} ajuste(s) reaplicado(s), {already} já estavam no lugar, {failed} falha(s).'
    if failed_items:
        # "1 falha(s)" sozinho não dizia qual item, nem ao usuário nem ao suporte.
        names = [item['name'] for item in failed_items]
        detail += ' Falhou: ' + '; '.join(names[:3]) + (' e outros' if len(names) > 3 else '') + '.'
    return finish(outcome, profile=profile, changed=changed, already=already, failed=failed,
                  failed_items=failed_items[:10], restart=any(bool(r.get('restart')) for r in tweaks),
                  detail=detail)
