#!/usr/bin/python
# -*- coding: UTF-8 -*-
import time
import os

###########################################################
def get_free_port(start_port=10000):
    all_port = os.popen('netstat -na').read()
    for i in range(int(start_port), 60000):
        if str(i) not in all_port and i % 500 != 0 and i not in ServerPool.get_instance().tcp_servers_pool:
            return i


def speed_format(byte_size):
    i = 0
    while abs(byte_size) >= 1024:
        byte_size = byte_size / 1024
        i += 1
        if i == 4:
            break
    units = ["B", "KB", "MB", "GB", "TB"]
    speed = '%.2f_%s/s' % (byte_size, units[i])
    return speed


def get_speed(netname="eth0"):
    # return speed_format(10240)
    f = open("/proc/net/dev")
    lines = f.readlines()
    f.close()
    for line in lines[2:]:
        con = line.split()
        if netname in con[0]:
            last_bytes = long(long(con[8]) > long(con[9]) and con[8] or con[9])  # 部分电脑split后出错
            break
    time.sleep(5)
    f = open("/proc/net/dev")
    lines = f.readlines()
    f.close()
    rate_bytes = 0.00
    for line in lines[2:]:
        con = line.split()
        if netname in con[0]:
            rate_bytes = (long(long(con[8]) > long(con[9]) and con[8] or con[9]) - last_bytes) / 5
            break
    return speed_format(rate_bytes)

###############################################################