"""Standard-user launcher; no cleanup, forced process termination or automatic tweaks."""
from pathlib import Path
import os
import sys
import time

def main():
    if '--smoke-test' in sys.argv:
        from azor_package_check import main as check
        return check()
    if '--logon-apply' in sys.argv:
        # Tarefa agendada do login: aplica o modo escolhido e sai, sem janela.
        from azor_autostart import run_logon
        return run_logon()
    if '--elevated-request' in sys.argv:
        from azor_elevation import worker_main
        return worker_main(sys.argv[sys.argv.index('--elevated-request')+1])
    import azor_server as server
    import azor_core as core
    # Only the normal UI process owns this lock. A privileged operation is separate.
    stream=(core.DATA_DIR/'application.lock').open('a+b')
    try:
        import msvcrt
        stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
        try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                info=server.read_runtime()
                url=str(info.get('url') or '')
                if url and server.probe_url(url)[0]:
                    server.open_ui(url)
                    return
                time.sleep(.3)
            raise RuntimeError('O AZOR já está aberto, mas ainda não respondeu. Aguarde a sessão atual; nenhum processo foi encerrado.')
        try:server.main()
        finally:
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
    finally:stream.close()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        if '--smoke-test' in sys.argv or '--logon-apply' in sys.argv:
            if sys.stderr:print(str(exc),file=sys.stderr)
            raise SystemExit(1)
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(exc),'AZOR — Não foi possível abrir',0x10)
        else:raise
