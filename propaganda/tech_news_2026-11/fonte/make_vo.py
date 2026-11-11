"""Gera a narração de cada notícia com o Kokoro (voz pm_alex) e a linha do tempo usada pelo vídeo.

Uso: python make_vo.py <pasta do modelo> <índice da notícia>
Saída: vo/s<N>.wav (narração inteira) e vo/s<N>.json (início e duração de cada parte).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

MODEL, N = Path(sys.argv[1]), int(sys.argv[2])
HERE = Path(__file__).parent
OUT = HERE / 'vo'
OUT.mkdir(exist_ok=True)

# lê STORIES e VO_END direto do news_data.js (via node, para não duplicar o texto)
js = subprocess.run(['node', '--input-type=module', '-e',
                     f"import('{(HERE / 'news_data.js').as_uri()}').then(m => console.log(JSON.stringify({{s: m.STORIES[{N}], end: m.VO_END}})))"],
                    capture_output=True, text=True, check=True).stdout
data = json.loads(js)
s, vo = data['s'], data['s']['vo']
parts = [('head', vo['head'])] + [(f'f{i}', f) for i, f in enumerate(vo['facts'])]
if 'path' in vo:
    parts.append(('path', vo['path']))
parts += [('take', vo['take']), ('end', data['end'])]

k = Kokoro(str(MODEL / 'kokoro.onnx'), str(MODEL / 'voices.bin'))
SR = 24000
LEAD, GAP = 0.6, {'head': 0.55, 'f0': 0.45, 'f1': 0.45, 'f2': 0.6, 'path': 0.6, 'take': 0.7, 'end': 0.0}
t = LEAD
audio = [np.zeros(int(LEAD * SR), dtype=np.float32)]
segs = []
for key, text in parts:
    a, sr = k.create(text, voice='pm_alex', speed=1.02, lang='pt-br')
    assert sr == SR
    # tira o silêncio do começo e do fim que o modelo às vezes deixa
    idx = np.where(np.abs(a) > 0.01)[0]
    a = a[max(0, idx[0] - 240): idx[-1] + 2400] if len(idx) else a
    d = len(a) / SR
    segs.append({'k': key, 'start': round(t, 3), 'dur': round(d, 3)})
    gap = GAP.get(key, 0.45)
    audio += [a.astype(np.float32), np.zeros(int(gap * SR), dtype=np.float32)]
    t += d + gap
total = t + 1.4
audio.append(np.zeros(int(1.4 * SR), dtype=np.float32))
sf.write(OUT / f's{N}.wav', np.concatenate(audio), SR)
(OUT / f's{N}.json').write_text(json.dumps({'segs': segs, 'D': round(total, 2)}, ensure_ascii=False, indent=1))
print(f's{N}', round(total, 2), [(x['k'], x['start'], x['dur']) for x in segs])
