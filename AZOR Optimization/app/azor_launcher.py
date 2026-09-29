"""Ponto de entrada do AZOR (chamado pelo ABRIR AZOR.bat).

  (sem argumentos)       abre a interface; se já estiver aberta, só traz a janela
  --no-window            sobe o motor (e o ícone da bandeja) sem abrir a janela
  --ui-only              só abre a janela quando o motor responder (usado pelo .bat
                         para a janela abrir como usuário comum e o motor como admin)
  --logon-apply          tarefa do login: reaplica o modo salvo e sai, sem janela
  --elevated-request F   processo elevado que executa uma única operação pedida
"""
import os
import sys
import time


def main():
    if '--logon-apply' in sys.argv:
        from azor_autostart import run_logon
        return run_logon()
    if '--elevated-request' in sys.argv:
        from azor_elevation import worker_main
        return worker_main(sys.argv[sys.argv.index('--elevated-request') + 1])
    import azor_server as server
    import azor_core as core
    if '--ui-only' in sys.argv:
        # Espera o motor elevado subir (o usuário ainda pode estar no aviso do UAC).
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            url = str(server.read_runtime().get('url') or '')
            if url and server.probe_url(url)[0]:
                server.open_ui(url)
                return
            time.sleep(0.4)
        return
    # Só a interface segura este lock: uma segunda abertura reaproveita a janela.
    stream = (core.DATA_DIR / 'application.lock').open('a+b')
    try:
        import msvcrt
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                url = str(server.read_runtime().get('url') or '')
                if url and server.probe_url(url)[0]:
                    if '--no-window' not in sys.argv:
                        server.open_ui(url)
                    return
                time.sleep(0.3)
            raise RuntimeError('O AZOR já está aberto e ainda não respondeu. Aguarde alguns segundos.')
        try:
            server.main()
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        stream.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if '--logon-apply' in sys.argv:
            raise SystemExit(1)
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), 'AZOR - não foi possível abrir', 0x10)
        else:
            raise
