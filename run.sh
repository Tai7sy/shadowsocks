#!/bin/bash
cd `dirname $0`
eval $(ps -ef | grep "[0-9] python server\\.py m" | awk '{print "kill "$2}')
#ps -ef | grep ssserver.log| grep -v grep | awk '{print $2}' | xargs kill -s 9
ulimit -n 512000
#nohup python server.py m >> ssserver.log 2>&1 &
#nohup tail -F ssserver.log | python utils/autoban.py >> banip.log 2>&1 &
nohup python server.py m >/dev/null 2>&1 &
echo 'runing'

