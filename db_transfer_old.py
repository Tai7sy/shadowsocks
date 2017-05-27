#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import time
import sys
from server_pool import ServerPool
import api_config
import traceback
from shadowsocks import common
import os
import json
import urllib2


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
db_instance = None


class DbTransfer(object):
    def __init__(self):
        import threading
        self.event = threading.Event()
        self.last_get_transfer = {}  # 上一次的实际流量
        self.last_update_transfer = {}  # 上一次更新到的流量（小于等于实际流量）
        self.pull_ok = False  # 记录是否已经拉出过数据
        self.mu_ports = {}

    def update_all_user(self):
        # 更新用户流量到数据库
        if self.pull_ok is False:
            return
        # print '更新用户流量到数据库\n'
        last_transfer = self.last_update_transfer
        curr_transfer = ServerPool.get_instance().get_servers_transfer()  # 总流量
        # 上次和本次的增量
        dt_transfer = {}
        server_trans_all = 0
        online_count = 0
        for id in curr_transfer.keys():
            online_count = online_count + 1
            # print 'Now online_count %d  id:%d' % (online_count,id)
            if id in last_transfer:
                # print '%d in last : trans:%d' % (id,int((curr_transfer[id][0]+curr_transfer[id][1])/1024))
                if last_transfer[id][0] == curr_transfer[id][0] and last_transfer[id][1] == curr_transfer[id][1]:
                    continue
                # elif curr_transfer[id][0] == 0 and curr_transfer[id][1] == 0:
                elif last_transfer[id][0] <= curr_transfer[id][0] and last_transfer[id][1] <= curr_transfer[id][1]:
                    if (curr_transfer[id][0] + curr_transfer[id][1] - last_transfer[id][0] - last_transfer[id][1]) / 1024 < 10:  # 小于10KB  忽略 等待下一次
                        continue
                    dt_transfer[id] = [int((curr_transfer[id][0] - last_transfer[id][0]) * api_config.NOW_SER_TRANSFER_MUL),
                                       int((curr_transfer[id][1] - last_transfer[id][1]) * api_config.NOW_SER_TRANSFER_MUL)]
                    server_trans_all += (curr_transfer[id][0] - last_transfer[id][0]) + (curr_transfer[id][1] - last_transfer[id][1])
                else:
                    dt_transfer[id] = [int(curr_transfer[id][0] * api_config.NOW_SER_TRANSFER_MUL),
                                       int(curr_transfer[id][1] * api_config.NOW_SER_TRANSFER_MUL)]
            else:
                # if curr_transfer[id][0] == 0 and curr_transfer[id][1] == 0:
                # print '%d not in last : trans:%d' % (id,int((curr_transfer[id][0]+curr_transfer[id][1])/1024))
                if int((curr_transfer[id][0] + curr_transfer[id][1]) / 1024) < 10:  # 小于10KB  忽略 等待下一次
                    # print '%d not in last : upload+download < 10 #1' % id
                    continue
                dt_transfer[id] = [int(curr_transfer[id][0] * api_config.NOW_SER_TRANSFER_MUL),
                                   int(curr_transfer[id][1] * api_config.NOW_SER_TRANSFER_MUL)]
                # print 'Port: %d  upload: %d  download: %d  Rate: %f#1' % (id,curr_transfer[id][0],curr_transfer[id][1],Config.NOWSER_TRANSFER_MUL)
                server_trans_all += curr_transfer[id][0] + curr_transfer[id][1]
            # print 'dt_transfer :%s' % dt_transfer
            # print 'last_transfer :%s' % last_transfer

        update_server = "http://%s%supdateserver.php?sk=%s&flow=%d&count=%d&net=%s" % (api_config.API_HOST, api_config.API_PATH, api_config.API_TOKEN, (server_trans_all + 1) / 1024, online_count, get_speed(api_config.NETNAME))
        print update_server
        urllib2.urlopen(update_server)
        data = {'list': {}, 'count': 0}
        for id in dt_transfer.keys():
            data['list'][str(id)] = int((dt_transfer[id][0] + dt_transfer[id][1]) / 1024)
            data['count'] = data['count'] + 1
        if data['count'] == 0:
            # print '更新用户流量到数据库 - 无数据 \n'
            return
        data['ret'] = 'yes'
        post_data = json.dumps(data)
        # print post_data
        urllib2.urlopen("http://%s%supdateuser.php?sk=%s" % (api_config.API_HOST, api_config.API_PATH, api_config.API_TOKEN), post_data)

        self.last_get_transfer = curr_transfer

    def pull_db_all_user(self):
        # 数据库所有用户信息
        print '获取数据库所有用户信息\n'
        print "http://%s%spulluser.php?sk=%s" % (api_config.API_HOST, api_config.API_PATH, api_config.API_TOKEN)
        try:
            user_list = json.loads(urllib2.urlopen("http://%s%spulluser.php?sk=%s" % (api_config.API_HOST, api_config.API_PATH, api_config.API_TOKEN)).read())
            if user_list['ret'] == 'no':  # 说明此服务器已经禁用  (小于1G)
                print 'server trans used out'
                return -1
        except Exception as e:
            print 'pull_db_all_user Exception: %s' % e
            return -1

        if user_list['ret'] != 'yes':  # 传输出现错误
            print 'pull error #1'
            return -2
        try:
            rows = user_list['list']
            print rows
        except Exception as e:
            print 'pull error #2'
            rows = []
        return rows

    def del_server_out_of_bound_safe(self, last_rows, rows):
        # print '停止超流量的服务 + 启动没超流量的服务\n'
        # 停止超流量的服务
        # 启动没超流量的服务
        cur_servers = {}  # 就是rows = = (经过了一点处理)
        cp_servers = {}
        for row in rows:
            allow = True  # 禁用的用户不会出现在此列表中
            # logging.error('用户: %d  状态：%s\n' % (row['port'],allow and 'ok' or 'stop'))
            passwd = common.to_bytes(row['passwd'])
            if int(row['port']) == 0 or int(row['port']) >= 100000:
                if int(row['port']) >= 100000:
                    newport = get_free_port(int(row['port']) % 100000)  # 从1xxxxx 里面的 xxxxx开始开通用户
                else:
                    newport = get_free_port()
                print '\n\nNew Server/1: %s ' % row['port']
                logging.info('db start server at random port [%s] pass [%s]' % (row['port'], passwd))
                ServerPool.get_instance().new_server(newport, passwd)
                new_user_url = "http://%s%snewuser.php?sk=%s&p=%d&u=%s" % (api_config.API_HOST, api_config.API_PATH, api_config.API_TOKEN, newport, row['u'])
                print "New user Success %s" % new_user_url
                urllib2.urlopen(new_user_url)
                row['port'] = '%d' % newport

            port = row['port']

            if port not in cur_servers:
                cur_servers[port] = passwd
            else:
                logging.error('more than one user use the same port [%s]' % (port,))
                continue

            if ServerPool.get_instance().server_is_run(port) > 0:
                if (port in ServerPool.get_instance().tcp_servers_pool and ServerPool.get_instance().tcp_servers_pool[port]._config['password'] != passwd) \
                        or (port in ServerPool.get_instance().tcp_ipv6_servers_pool and ServerPool.get_instance().tcp_ipv6_servers_pool[port]._config['password'] != passwd):
                    # password changed
                    print '\n\npassword changed: %s pass:%s' % (port, passwd)
                    logging.info('db stop server at port [%s] reason: password changed' % (port,))
                    ServerPool.get_instance().cb_del_server(port)
                    cp_servers[port] = passwd

            elif allow and ServerPool.get_instance().server_run_status(port) is False:
                # New server
                print '\n\nNew Server/2: %s ' % port
                logging.info('db start server at port [%s] pass [%s]' % (port, passwd))
                ServerPool.get_instance().new_server(port, passwd)

        for row in last_rows:
            if row['port'] in cur_servers:
                pass
            else:
                logging.info('db stop server at port [%s] reason: port not exist' % (row['port']))
                ServerPool.get_instance().cb_del_server(row['port'])

        if len(cp_servers) > 0:  # 密码不对修改密码的
            from shadowsocks import eventloop
            self.event.wait(eventloop.TIMEOUT_PRECISION + eventloop.TIMEOUT_PRECISION / 2)
            for port in cp_servers.keys():
                passwd = cp_servers[port]
                logging.info('db start server at port [%s] pass [%s] (Change PASS)' % (port, passwd))
                ServerPool.get_instance().new_server(port, passwd)

    @staticmethod
    def del_servers():
        for port in [v for v in ServerPool.get_instance().tcp_servers_pool.keys()]:
            if ServerPool.get_instance().server_is_run(port) > 0:
                ServerPool.get_instance().cb_del_server(port)
        for port in [v for v in ServerPool.get_instance().tcp_ipv6_servers_pool.keys()]:
            if ServerPool.get_instance().server_is_run(port) > 0:
                ServerPool.get_instance().cb_del_server(port)

    @staticmethod
    def thread_db(obj):
        import socket
        global db_instance
        socket.setdefaulttimeout(60)
        last_rows = []
        db_instance = obj()
        try:
            while True:
                reload(api_config)
                try:
                    # logging.info('Start')
                    db_instance.update_all_user()  # 更新用户流量到数据库
                    rows = db_instance.pull_db_all_user()  # 数据库所有用户信息
                    if rows == -1:
                        raise Exception
                    if rows == -2:
                        rows = last_rows
                    db_instance.del_server_out_of_bound_safe(last_rows, rows)  # 增加/删除  端口
                    last_rows = rows
                except Exception as e:
                    trace = traceback.format_exc()
                    logging.error(trace)
                # logging.warn('db thread except:%s' % e)
                print 'wait %d \n\n\n\n\n\n' % api_config.API_UPDATE_TIME
                if db_instance.event.wait(api_config.API_UPDATE_TIME) or not ServerPool.get_instance().thread.is_alive():
                    break
        except KeyboardInterrupt as e:
            pass
        db_instance.del_servers()
        ServerPool.get_instance().stop()
        db_instance = None

    @staticmethod
    def thread_db_stop():
        global db_instance
        db_instance.event.set()
