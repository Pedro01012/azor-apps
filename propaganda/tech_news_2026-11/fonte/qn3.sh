#!/bin/bash
cd /tmp/claude-0/-home-user-azor-apps/e7bcfb17-7547-53c2-884c-d801e712bfa8/scratchpad/anim
run(){ D=$(python3 -c "import json;print(json.load(open('vo/s$1.json'))['D'])"); Q="s=$1" DUR=$D ./rfilm.sh news_vid3.html vo$1 2 && ./finish_vo.sh vo$1 vo/s$1.wav; }
run 0 & run 1 & wait
run 2 & run 3 & wait
