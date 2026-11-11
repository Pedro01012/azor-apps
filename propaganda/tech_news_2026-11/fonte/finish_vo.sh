#!/bin/bash
# uso: ./finish_vo.sh nome vo/sN.wav -> mistura a narração com a cama sonora e junta com o vídeo (out/nome.mp4)
cd "$(dirname "$0")" || exit 1
N=$1; VO=$2
PY=../venv/bin/python; [ -x "$PY" ] || PY=python3
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 out/$N.video.mp4)
$PY -I sound2.py out/$N.sfx.json out/$N.bed.wav $D > out/$N.sound.log 2>&1 || { echo "$N SOUND FAIL"; cat out/$N.sound.log; exit 1; }
ffmpeg -v error -y -i out/$N.video.mp4 -i out/$N.bed.wav -i $VO -filter_complex "
[2]aresample=48000,highpass=f=70,equalizer=f=220:t=q:w=1:g=-2,equalizer=f=3800:t=q:w=1.2:g=2.5,acompressor=threshold=-20dB:ratio=3:attack=6:release=120:makeup=3,pan=stereo|c0=c0|c1=c0,asplit=2[v][sc];
[1]volume=0.55[b];[b][sc]sidechaincompress=threshold=0.02:ratio=8:attack=30:release=400[bd];
[bd][v]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=9[a]" \
 -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 17 -maxrate 11M -bufsize 18M -pix_fmt yuv420p -c:a aac -b:a 256k -shortest -movflags +faststart out/$N.mp4 && echo "$N FINAL OK $(stat -c %s out/$N.mp4)"
