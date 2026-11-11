#!/bin/bash
# uso: ./finish.sh nome  -> gera o som a partir dos eventos e junta com o vídeo (out/nome.mp4)
cd "$(dirname "$0")" || exit 1
N=$1
PY=../venv/bin/python; [ -x "$PY" ] || PY=python3
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 out/$N.video.mp4)
$PY -I sound2.py out/$N.sfx.json out/$N.wav $D > out/$N.sound.log 2>&1 || { echo "$N SOUND FAIL"; cat out/$N.sound.log; exit 1; }
ffmpeg -v error -y -i out/$N.video.mp4 -i out/$N.wav -c:v libx264 -preset slow -crf 17 -maxrate 11M -bufsize 18M -pix_fmt yuv420p -c:a aac -b:a 256k -af loudnorm=I=-14:TP=-1:LRA=11 -shortest -movflags +faststart out/$N.mp4 && echo "$N FINAL OK $(stat -c %s out/$N.mp4)"
