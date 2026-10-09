#!/bin/bash
# uso: stills.sh pagina.html t1,t2,... saida.jpg [colunas]
cd "$(dirname "$0")"
rm -rf _st && NODE_PATH=/opt/node22/lib/node_modules node render3.js "$1" 1080 1920 30 _st "$2" 2>&1 | grep -E "ERR|rror" | head -5
i=0; for f in $(ls _st/s_*.jpg | sed 's/_st\/s_//;s/.jpg//' | sort -n); do cp _st/s_$f.jpg _st/o_$(printf %02d $i).jpg; i=$((i+1)); done
n=$(ls _st/o_*.jpg | wc -l); cols=${4:-5}; cols=$(( n < cols ? n : cols )); rows=$(( (n + cols - 1) / cols ))
ffmpeg -v error -y -i _st/o_%02d.jpg -vf "scale=360:-1,tile=${cols}x${rows}" -frames:v 1 "$3"
