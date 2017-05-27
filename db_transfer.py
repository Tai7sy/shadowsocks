#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import time
import func,urllib2,json
from server_pool import ServerPool
import traceback
from shadowsocks import common, shell, lru_cache, obfs
from configloader import load_config, get_config

db_instance = None

class TransferBase(object):
    def __init__(self):
        import threading
        self.event = threading.Event()
        self.key_list = ['port', 'u', 'd', 'transfer_enable', 'passwd', 'enable']
        self.last_get_transfer = {} #上一次的实际流量
        self.last_update_transfer = {} #上一次更新到的流量（小于等于实际流量）
        self.force_update_transfer = set() #强制推入数据库的ID
        self.port_uid_table = {} #端口到uid的映射（仅v3以上有用）
        self.onlineuser_cache = lru_cache.LRUCache(timeout=60*30) #用户在线状态记录
        self.pull_ok = False #记录是否已经拉出过数据

    def load_cfg(self):
        pass

    def push_db_all_user(self):
        if self.pull_ok is False:
            return
        #更新用户流量到数据库
        last_transfer = self.last_update_transfer
        curr_transfer = ServerPool.get_instance().get_servers_transfer()
        #上次和本次的增量
        dt_transfer = {}
        for id in self.force_update_transfer: #此表中的用户统计上次未计入的流量
            if id in self.last_get_transfer and id in last_transfer:
                dt_transfer[id] = [self.last_get_transfer[id][0] - last_transfer[id][0], self.last_get_transfer[id][1] - last_transfer[id][1]]

        for id in curr_transfer.keys():
            if id in self.force_update_transfer :
                continue
            #算出与上次记录的流量差值，保存于dt_transfer表
            if id in last_transfer:
                if curr_transfer[id][0] + curr_transfer[id][1] - last_transfer[id][0] - last_transfer[id][1] <= 0:
                    continue
                dt_transfer[id] = [curr_transfer[id][0] - last_transfer[id][0],
                                curr_transfer[id][1] - last_transfer[id][1]]
            else:
                if curr_transfer[id][0] + curr_transfer[id][1] <= 0:
                    continue
                dt_transfer[id] = [curr_transfer[id][0], curr_transfer[id][1]]

            #有流量的，先记录在线状态
            if id in self.last_get_transfer:
                if curr_transfer[id][0] + curr_transfer[id][1] > self.last_get_transfer[id][0] + self.last_get_transfer[id][1]:
                    self.onlineuser_cache[id] = curr_transfer[id][0] + curr_transfer[id][1]
            else:
                self.onlineuser_cache[id] = curr_transfer[id][0] + curr_transfer[id][1]

        self.onlineuser_cache.sweep()

        update_transfer = self.update_all_user(dt_transfer) #返回有更新的表
        for id in update_transfer.keys(): #其增量加在此表
            if id not in self.force_update_transfer: #但排除在force_update_transfer内的
                last = self.last_update_transfer.get(id, [0,0])
                self.last_update_transfer[id] = [last[0] + update_transfer[id][0], last[1] + update_transfer[id][1]]
        self.last_get_transfer = curr_transfer
        for id in self.force_update_transfer:
            if id in self.last_update_transfer:
                del self.last_update_transfer[id]
            if id in self.last_get_transfer:
                del self.last_get_transfer[id]
        self.force_update_transfer = set()

    def del_server_out_of_bound_safe(self, last_rows, rows):
        #停止超流量的服务
        #启动没超流量的服务
        cur_servers = {}
        new_servers = {}
        allow_users = {}
        for row in rows:

            passwd = common.to_bytes(row['passwd'])
            if hasattr(passwd, 'encode'):
                passwd = passwd.encode('utf-8')

            cfg = {'password': passwd}


            read_config_keys = ['method', 'obfs', 'obfs_param', 'protocol', 'protocol_param', 'forbidden_ip', 'forbidden_port', 'speed_limit_per_con', 'speed_limit_per_user']
            for name in read_config_keys:
                if name in row and row[name]:
                    cfg[name] = row[name]

            merge_config_keys = ['password'] + read_config_keys
            for name in cfg.keys():
                if hasattr(cfg[name], 'encode'):
                    try:
                        cfg[name] = cfg[name].encode('utf-8')
                    except Exception as e:
                        logging.warning('encode cfg key "%s" fail, val "%s"' % (name, cfg[name]))

            if int(row['port']) == 0 or int(row['port']) >= 100000:
                if int(row['port']) >= 100000:
                    newport = func.get_free_port(int(row['port']) % 100000)  # 从1xxxxx 里面的 xxxxx开始开通用户
                else:
                    newport = func.get_free_port()
                print '\n\nNew Server/1: %s ' % row['port']
                row['port'] = '%d' % newport
                self.new_server(newport, passwd, cfg)

                new_user_url = "http://%s%snewuser.php?sk=%s&p=%d&u=%s" % (get_config().API_HOST, get_config().API_PATH, get_config().API_TOKEN, newport, row['u'])
                print "New user Success %s" % new_user_url
                urllib2.urlopen(new_user_url)


            port = row['port']
            if 'u' in row: #uid 与 port 映射
                self.port_uid_table[row['port']] = row['u']
            if port not in cur_servers:
                cur_servers[port] = passwd
            else:
                logging.error('more than one user use the same port [%s]' % (port,))
                continue


            allow_users[port] = passwd

            cfg_changed = False
            if port in ServerPool.get_instance().tcp_servers_pool:
                relay = ServerPool.get_instance().tcp_servers_pool[port]
                for name in merge_config_keys:
                    if name in cfg and not self.cmp(cfg[name], relay._config[name]):
                        cfg_changed = True
                        break
            if not cfg_changed and port in ServerPool.get_instance().tcp_ipv6_servers_pool:
                relay = ServerPool.get_instance().tcp_ipv6_servers_pool[port]
                for name in merge_config_keys:
                    if name in cfg and not self.cmp(cfg[name], relay._config[name]):
                        cfg_changed = True
                        break

            if ServerPool.get_instance().server_is_run(port) > 0:
                if cfg_changed:
                    logging.info('db stop server at port [%s] reason: config changed: %s' % (port, cfg))
                    ServerPool.get_instance().cb_del_server(port)
                    self.force_update_transfer.add(port)
                    new_servers[port] = (passwd, cfg)
            elif 0 < port < 65536 and ServerPool.get_instance().server_run_status(port) is False:
                self.new_server(port, passwd, cfg)

        for row in last_rows:
            if row['port'] in cur_servers:
                pass
            else:
                logging.info('db stop server at port [%s] reason: port not exist' % (row['port']))
                ServerPool.get_instance().cb_del_server(row['port'])
                self.clear_cache(row['port'])
                if row['port'] in self.port_uid_table:
                    del self.port_uid_table[row['port']]

        if len(new_servers) > 0:
            from shadowsocks import eventloop
            self.event.wait(eventloop.TIMEOUT_PRECISION + eventloop.TIMEOUT_PRECISION / 2)
            for port in new_servers.keys():
                passwd, cfg = new_servers[port]
                self.new_server(port, passwd, cfg)

        logging.debug('db allow users %s \n' % allow_users)


    def clear_cache(self, port):
        if port in self.force_update_transfer: del self.force_update_transfer[port]
        if port in self.last_get_transfer: del self.last_get_transfer[port]
        if port in self.last_update_transfer: del self.last_update_transfer[port]

    def new_server(self, port, passwd, cfg):
        protocol_ = cfg.get('protocol', ServerPool.get_instance().config.get('protocol', 'origin'))
        method_ = cfg.get('method', ServerPool.get_instance().config.get('method', 'rc4-md5'))
        obfs_ = cfg.get('obfs', ServerPool.get_instance().config.get('obfs', 'http_simple_compatible'))
        logging.info('db start server at port [%s] pass [%s] protocol [%s] method [%s] obfs [%s]' % (port, passwd, protocol_, method_, obfs_))
        ServerPool.get_instance().new_server(port, cfg)

    def cmp(self, val1, val2):
        if type(val1) is bytes:
            val1 = common.to_str(val1)
        if type(val2) is bytes:
            val2 = common.to_str(val2)
        return val1 == val2

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
        import time
        global db_instance
        timeout = 60
        socket.setdefaulttimeout(timeout)
        last_rows = []
        db_instance = obj()
        ServerPool.get_instance()
        shell.log_shadowsocks_version()

        try:
            import resource
            logging.info('current process RLIMIT_NOFILE resource: soft %d hard %d'  % resource.getrlimit(resource.RLIMIT_NOFILE))
        except:
            pass

        try:
            while True:
                load_config()
                try:
                    db_instance.push_db_all_user()
                    rows = db_instance.pull_db_all_user()
                    if rows == -1:
                        raise Exception
                    elif rows == -2:
                        rows = last_rows
                    elif rows:
                        db_instance.pull_ok = True
                    db_instance.del_server_out_of_bound_safe(last_rows, rows)
                    last_rows = rows
                except Exception as e:
                    trace = traceback.format_exc()
                    logging.error(trace)
                    #logging.warn('db thread except:%s' % e)
                if db_instance.event.wait(get_config().API_UPDATE_TIME) or not ServerPool.get_instance().thread.is_alive():
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

class DbTransfer(TransferBase):
    def __init__(self):
        super(DbTransfer, self).__init__()
        self.user_pass = {} #记录更新此用户流量时被跳过多少次

    def update_all_user(self, dt_transfer):
        update_transfer = {}
        server_trans_all = 0
        online_count = 0


        last_time = time.time()

        for id in dt_transfer.keys():
            online_count = online_count + 1
            transfer = dt_transfer[id]
            #小于最低更新流量的先不更新
            update_trs = 1024 * (2048 - self.user_pass.get(id, 0) * 64)
            if transfer[0] + transfer[1] < update_trs and id not in self.force_update_transfer:
                self.user_pass[id] = self.user_pass.get(id, 0) + 1
                print 'Port: %d  upload: %d  download: %d  Rate: %f#1 , too less wait for next' % (id, transfer[0], transfer[1], get_config().NOW_SER_TRANSFER_MUL)
                continue
            if id in self.user_pass:
                del self.user_pass[id]

            server_trans_all += transfer[0] + transfer[1]
            update_transfer[id] = [int(transfer[0] * get_config().NOW_SER_TRANSFER_MUL),
                                   int(transfer[1] * get_config().NOW_SER_TRANSFER_MUL)]

            print 'Port: %d  upload: %d  download: %d  Rate: %f#1' % (id,transfer[0],transfer[1],get_config().NOW_SER_TRANSFER_MUL)

        update_server = "http://%s%supdateserver.php?sk=%s&flow=%d&count=%d&net=%s" % (get_config().API_HOST, get_config().API_PATH, get_config().API_TOKEN, (server_trans_all + 1) / 1024, online_count, func.get_speed(get_config().NETNAME))
        print update_server
        urllib2.urlopen(update_server)
        data = {'list': {}, 'count': 0}
        for id in update_transfer.keys():
            data['list'][str(id)] = int((update_transfer[id][0] + update_transfer[id][1]) / 1024)
            data['count'] = data['count'] + 1
        if data['count'] == 0:
            print '更新用户流量到数据库 - 无数据 \n'
            return update_transfer

        data['ret'] = 'yes'
        post_data = json.dumps(data)
        # print post_data
        urllib2.urlopen("http://%s%supdateuser.php?sk=%s" % (get_config().API_HOST, get_config().API_PATH, get_config().API_TOKEN), post_data)

        return update_transfer

    def pull_db_all_user(self):
        print '\n获取数据库所有用户信息'
        print "http://%s%spulluser.php?sk=%s" % (get_config().API_HOST, get_config().API_PATH, get_config().API_TOKEN)
        try:
            user_list = json.loads(urllib2.urlopen("http://%s%spulluser.php?sk=%s" % (get_config().API_HOST, get_config().API_PATH, get_config().API_TOKEN)).read())
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
