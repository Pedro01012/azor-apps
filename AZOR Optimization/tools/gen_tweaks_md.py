"""Gera o TWEAKS.md a partir do catálogo real do motor (não escreva a lista à mão).

Uso: runtime\\python.exe tools\\gen_tweaks_md.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from azor_modules import engine, gamer  # noqa: E402

BOOST = {'recomendado': 'Recomendado + Extremo', 'extremo': 'Só Extremo', None: '—'}


def main():
    data = engine.arsenal('agressivo')
    tasks = data['tasks']
    lines = ['# Tweaks do AZOR', '',
             'Lista gerada do catálogo real do app (`tools/gen_tweaks_md.py`). Cada ajuste é gravado, relido '
             'e só conta como aplicado se o Windows confirmar; o valor de antes fica guardado para desfazer.', '',
             f'Total: **{len(tasks)}** ajustes.', '',
             '| Selo | Significa |', '|---|---|',
             '| +FPS | mais quadros por segundo |', '| -DELAY | clique/tecla/movimento chegam antes na tela |',
             '| -STUTTER | menos travadinhas e quedas de 1% low |', '| PING | conexão mais estável no jogo |',
             '| +LEVE | menos processos e serviços gastando CPU/RAM |', '']
    for goal in gamer.GOALS:
        items = [t for t in tasks if t.get('goal') == goal['id']]
        if not items:
            continue
        lines += [f"## {goal['label']}", '', goal['hint'], '',
                  '| Ajuste | O que dá | BOOST | Reinicia | Desfaz |', '|---|---|---|---|---|']
        for t in sorted(items, key=lambda x: (-int(x.get('impact') or 1), x.get('title') or x['name'])):
            title = (t.get('title') or t['name']).replace('|', '/')
            simple = (t.get('simple') or t.get('description') or '').replace('|', '/')
            badges = ' '.join(f'`{b}`' for b in t.get('badges') or [])
            boost = 'Teste manual' if t.get('ab_test') else BOOST.get(t.get('boost'), '—')
            undo = 'não' if t.get('one_way') or not t.get('reversible') else 'sim'
            lines.append(f"| **{title}**<br>{simple} | {badges} | {boost} | {'sim' if t.get('restart') else 'não'} | {undo} |")
        lines.append('')
    (ROOT / 'TWEAKS.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'TWEAKS.md: {len(tasks)} ajustes.')


if __name__ == '__main__':
    main()
