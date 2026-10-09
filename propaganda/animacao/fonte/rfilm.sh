#!/bin/bash
# uso: ./rfilm.sh pagina.html nome [processos]  -> out/nome.video.mp4 + out/nome.sfx.json
cd "$(dirname "$0")" || exit 1
PAGE=$1; NAME=$2; P=${3:-2}
mkdir -p out
D=$(grep -o "const D = [0-9.]*" $PAGE | head -1 | awk '{print $4}')
N=$(python3 -c "print(round($D*30))")
STEP=$(( (N + P - 1) / P ))
rm -f out/$NAME.part*.mp4 out/$NAME.list
for i in $(seq 0 $((P-1))); do
  F=$((i*STEP)); T=$(( (i+1)*STEP < N ? (i+1)*STEP : N ))
  FROM=$F TO=$T node render3.js $PAGE 1080 1920 30 out/$NAME.part$i.mp4 > out/$NAME.part$i.log 2>&1 &
  echo "file '$NAME.part$i.mp4'" >> out/$NAME.list
done
wait
ffmpeg -v error -y -f concat -safe 0 -i out/$NAME.list -c copy out/$NAME.video.mp4 && cp out/$NAME.part0.sfx.json out/$NAME.sfx.json && echo "$NAME ok ($N quadros)"
