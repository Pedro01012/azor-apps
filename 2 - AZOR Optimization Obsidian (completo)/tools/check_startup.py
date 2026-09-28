"""Fast startup validation: parse local source without running optimization code."""
from pathlib import Path
import sys
import time


def check(root):
    payload = root / 'payload'
    required = [payload / name for name in (
        'azor_server.py', 'azor_core.py', 'azor_input_monitor.py',
        'web/index.html', 'web/app.js', 'web/styles.css', 'web/input-studio.css',
        'web/azor-theme.css', 'web/performance-center.js')]
    missing = [str(p.relative_to(root)) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError('Arquivos ausentes ou vazios: ' + ', '.join(missing))
    sources = sorted(payload.glob('*.py')) + sorted((payload / 'azor_modules').glob('*.py'))
    if not (payload / 'azor_modules' / 'engine.py').is_file():
        raise RuntimeError('Motor de ajustes ausente.')
    for source in sources:
        # compile creates only an in-memory code object: no imports, no Windows calls.
        compile(source.read_bytes(), str(source), 'exec')
    return len(sources)


if __name__ == '__main__':
    started = time.perf_counter()
    try:
        count = check(Path(__file__).resolve().parents[1])
        print(f'OK: {count} fontes Python e arquivos da interface conferidos em {time.perf_counter()-started:.2f}s.')
    except Exception as exc:
        print(f'Falha na abertura: {exc}', file=sys.stderr)
        sys.exit(1)
