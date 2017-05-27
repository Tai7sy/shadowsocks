#!/bin/bash
cd `dirname $0`
ps -ef | grep ssserver.log| grep -v grep | awk '{print $2}' | xargs kill -s 9
rm -rf /var/log/ssserver.log
nohup tail -F ssserver.log | python utils/autoban.py >log 2>log &