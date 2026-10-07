#!/bin/sh
# Mede o brilho de cada quadro da tela (lap_frames/) e grava lap_meta.js para o laptop.html.
ffmpeg -v error -framerate 30 -i lap_frames/f%05d.jpg -vf "scale=64:40,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=luma.txt" -f null -
python3 -c "
import re
v=[round(float(x)) for x in re.findall(r'YAVG=([0-9.]+)', open('luma.txt').read())]
open('lap_meta.js','w').write('window.LUMA=%s;window.NFR=%d;window.DURATION=23.2;'%(v,len(v)))
print(len(v), 'quadros')"
