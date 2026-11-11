#!/bin/bash
cd /tmp/claude-0/-home-user-azor-apps/e7bcfb17-7547-53c2-884c-d801e712bfa8/scratchpad/anim
run(){ Q="s=$1" DUR=$2 ./rfilm.sh news_vid.html news$1 2 && ./finish.sh news$1; }
run 0 20.6 & run 1 17.6 & wait
run 2 17.6 & run 3 17.6 & wait
