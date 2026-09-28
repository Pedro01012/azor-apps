"""Conferência rápida antes de abrir: os arquivos estão todos aqui e compilam?

Não importa nada do app e não toca no Windows: só compila o código em memória.
"""
from pathlib import Path
import sys
import time


def check(root):
    app = root / 'app'
    web = app / 'web'
    required = [app / 'azor_launcher.py', app / 'azor_server.py', app / 'azor_core.py', app / 'azor_modules' / 'engine.py',
                web / 'index.html', web / 'azor.css', web / 'js' / 'core.js', web / 'js' / 'app.js',
                web / 'assets' / 'Azor_icon.png']
    required += [web / 'js' / 'pages' / f'{name}.js' for name in
                 ('home', 'plan', 'tweaks', 'apps', 'cleanup', 'games', 'periph', 'hardware', 'repair', 'settings')]
    missing = [str(p.relative_to(root)) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError('Arquivos ausentes ou vazios: ' + ', '.join(missing))
    sources = sorted(app.glob('*.py')) + sorted((app / 'azor_modules').glob('*.py'))
    for source in sources:
        compile(source.read_bytes(), str(source), 'exec')
    return len(sources)


if __name__ == '__main__':
    started = time.perf_counter()
    try:
        count = check(Path(__file__).resolve().parents[1])
        print(f'OK: {count} arquivos conferidos em {time.perf_counter() - started:.2f}s.')
    except Exception as exc:
        print(f'Falha na abertura: {exc}', file=sys.stderr)
        sys.exit(1)
