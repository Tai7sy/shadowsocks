#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import time
import sys
from server_pool import ServerPool
import Config
import traceback
from shadowsocks import common
import os
import json
import urllib2
###########################################################
def getFreePort(startport=10000):
	allport=os.popen('netstat -na').read()
	for i in range(int(startport),60000):
		if(str(i) not in allport and i%500 != 0 and i not in ServerPool.get_instance().tcp_servers_pool):
			return i
def speedformat(bytesize):
	i=0
	while(abs(bytesize) >= 1024):
		bytesize=bytesize/1024
		i+=1
		if i==4:
			break
	units = ["B","KB","MB","GB","TB"]
	speed = '%.2f_%s/s' % (bytesize,units[i])
	return speed
def getspeed(netname="eth0"):
	#return speedformat(10240)
	f = open("/proc/net/dev")
	lines = f.readlines()
	f.close()
	for line in lines[2:]:
		con = line.split()
		if netname in con[0]:
			lastbytes = long(long(con[8])>long(con[9]) and con[8] or con[9])#部分电脑split后出错
			break
	time.sleep(5)
	f = open("/proc/net/dev")
	lines = f.readlines()
	f.close()
	ratebytes = 0.00
	for line in lines[2:]:
		con = line.split()
		if netname in con[0]:
			ratebytes = (long(long(con[8])>long(con[9]) and con[8] or con[9]) - lastbytes)/5
			break
	return speedformat(ratebytes)
###############################################################
db_instance = None

class DbTransfer(object):
	def __init__(self):
		import threading
		self.last_get_transfer = {}
		self.event = threading.Event()

	def update_all_user(self):
		#更新用户流量到数据库
		#print '更新用户流量到数据库\n'
		last_transfer = self.last_get_transfer
		curr_transfer = ServerPool.get_instance().get_servers_transfer()#总流量
		#上次和本次的增量
		dt_transfer = {}
		server_transall = 0
		online_count = 0
		for id in curr_transfer.keys():
			online_count = online_count + 1
			#print 'Now online_count %d  id:%d' % (online_count,id)
			if id in last_transfer:
				#print '%d in last : trans:%d' % (id,int((curr_transfer[id][0]+curr_transfer[id][1])/1024))
				if last_transfer[id][0] == curr_transfer[id][0] and last_transfer[id][1] == curr_transfer[id][1]:
					continue
				#elif curr_transfer[id][0] == 0 and curr_transfer[id][1] == 0:
				elif last_transfer[id][0] <= curr_transfer[id][0] and last_transfer[id][1] <= curr_transfer[id][1]:
					if (curr_transfer[id][0]+curr_transfer[id][1]-last_transfer[id][0]-last_transfer[id][1])/1024 < 10:#小于10KB  忽略 等待下一次
						continue
					dt_transfer[id] = [int((curr_transfer[id][0] - last_transfer[id][0]) * Config.NOWSER_TRANSFER_MUL),
										int((curr_transfer[id][1] - last_transfer[id][1]) * Config.NOWSER_TRANSFER_MUL)]
					server_transall += (curr_transfer[id][0] - last_transfer[id][0]) + (curr_transfer[id][1] - last_transfer[id][1])
				else:
					dt_transfer[id] = [int(curr_transfer[id][0] * Config.NOWSER_TRANSFER_MUL),
										int(curr_transfer[id][1] * Config.NOWSER_TRANSFER_MUL)]
			else:
				#if curr_transfer[id][0] == 0 and curr_transfer[id][1] == 0:
				#print '%d not in last : trans:%d' % (id,int((curr_transfer[id][0]+curr_transfer[id][1])/1024))
				if int((curr_transfer[id][0]+curr_transfer[id][1])/1024) < 10:#小于10KB  忽略 等待下一次
					#print '%d not in last : upload+download < 10 #1' % id
					continue
				dt_transfer[id] = [int(curr_transfer[id][0] * Config.NOWSER_TRANSFER_MUL),
									int(curr_transfer[id][1] * Config.NOWSER_TRANSFER_MUL)]
				#print 'Port: %d  upload: %d  download: %d  Rate: %f#1' % (id,curr_transfer[id][0],curr_transfer[id][1],Config.NOWSER_TRANSFER_MUL)
				server_transall += curr_transfer[id][0] + curr_transfer[id][1]
			#print 'dt_transfer :%s' % dt_transfer
			#print 'last_transfer :%s' % last_transfer

		updateserver="http://%s%supdateserver.php?sk=%s&flow=%d&count=%d&net=%s" % (Config.API_HOST,Config.API_PATH,Config.API_TOKEN,(server_transall+1)/1024,online_count,getspeed(Config.NETNAME))
		print updateserver
		urllib2.urlopen(updateserver)
		data = {}
		data['list'] = {}
		data['count'] = 0
		for id in dt_transfer.keys():
			data['list'][str(id)] = int((dt_transfer[id][0]+dt_transfer[id][1])/1024)
			data['count']=data['count']+1
		if data['count'] == 0:
			#print '更新用户流量到数据库 - 无数据 \n'
			return
		data['ret'] = 'yes'
		post_data = json.dumps(data)
		#print post_data
		urllib2.urlopen("http://%s%supdateuser.php?sk=%s" % (Config.API_HOST,Config.API_PATH,Config.API_TOKEN), post_data)

		self.last_get_transfer = curr_transfer

	def pull_db_all_user(self):
		#数据库所有用户信息
		#print '获取数据库所有用户信息\n'
		print "http://%s%spulluser.php?sk=%s" % (Config.API_HOST,Config.API_PATH,Config.API_TOKEN)
		try:
			userlist=json.loads(urllib2.urlopen("http://%s%spulluser.php?sk=%s" % (Config.API_HOST,Config.API_PATH,Config.API_TOKEN)).read())
			if(userlist['ret']=='no'):# 说明此服务器已经禁用  (小于1G)
				print 'server trans used out'
				return -1
		except Exception as e:
			#print 'pull_db_all_user Exception: %s' % e
			return -1

		if(userlist['ret']!='yes'):#传输出现错误
			#print 'pull error #1'
			return -2
		try:
			rows = userlist['list']
			print rows
		except Exception as e:
			#print 'pull error #2'
			rows = []
		
		return rows

	def del_server_out_of_bound_safe(self, last_rows, rows):
		#print '停止超流量的服务 + 启动没超流量的服务\n'
		#停止超流量的服务
		#启动没超流量的服务
		cur_servers = {} #就是rows = = (经过了一点处理)
		cp_servers = {}
		for row in rows:
			allow = True #禁用的用户不会出现在此列表中
			#logging.error('用户: %d  状态：%s\n' % (row['port'],allow and 'ok' or 'stop'))
			passwd = common.to_bytes(row['passwd'])
			if int(row['port']) == 0 or int(row['port'])>=100000:
				if int(row['port'])>=100000:
					newport=getFreePort(int(row['port'])%100000) #从1xxxxx 里面的 xxxxx开始开通用户
				else:
					newport=getFreePort()
				print '\n\nNew Server/1: %s ' % row['port']
				logging.info('db start server at random port [%s] pass [%s]' % (row['port'], passwd))
				ServerPool.get_instance().new_server(newport, passwd)
				newuseru = "http://%s%snewuser.php?sk=%s&p=%d&u=%s" % (Config.API_HOST,Config.API_PATH,Config.API_TOKEN,newport,row['u'])
				print "New user Success %s" % newuseru
				urllib2.urlopen(newuseru)
				row['port']='%d' % newport
				
			port = row['port']

			if port not in cur_servers:
				cur_servers[port] = passwd
			else:
				logging.error('more than one user use the same port [%s]' % (port,))
				continue

			if ServerPool.get_instance().server_is_run(port) > 0:
				if (port in ServerPool.get_instance().tcp_servers_pool and ServerPool.get_instance().tcp_servers_pool[port]._config['password'] != passwd) \
					or (port in ServerPool.get_instance().tcp_ipv6_servers_pool and ServerPool.get_instance().tcp_ipv6_servers_pool[port]._config['password'] != passwd):
					#password changed
					print '\n\npassword changed: %s pass:%s' % (port,passwd)
					logging.info('db stop server at port [%s] reason: password changed' % (port,))
					ServerPool.get_instance().cb_del_server(port)
					cp_servers[port] = passwd

			elif allow and ServerPool.get_instance().server_run_status(port) is False:
				#New server
				print '\n\nNew Server/2: %s ' % port
				logging.info('db start server at port [%s] pass [%s]' % (port, passwd))
				ServerPool.get_instance().new_server(port, passwd)

		for row in last_rows:
			if row['port'] in cur_servers:
				pass
			else:
				logging.info('db stop server at port [%s] reason: port not exist' % (row['port']))
				ServerPool.get_instance().cb_del_server(row['port'])

		if len(cp_servers) > 0:#密码不对修改密码的
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
		import time
		global db_instance
		socket.setdefaulttimeout(60)
		last_rows = []
		db_instance = obj()
		try:
			while True:
				reload(Config)
				try:
					#logging.info('Start')
					db_instance.update_all_user() #更新用户流量到数据库
					rows = db_instance.pull_db_all_user() #数据库所有用户信息 
					if(rows == -1):
						raise Exception
					if(rows == -2):
						rows = last_rows
					db_instance.del_server_out_of_bound_safe(last_rows, rows)#  增加/删除  端口
					last_rows = rows
				except Exception as e:
					trace = traceback.format_exc()
					logging.error(trace)
					#logging.warn('db thread except:%s' % e)
				print 'wait %d \n\n\n\n\n\n' % Config.API_UPDATE_TIME
				if db_instance.event.wait(Config.API_UPDATE_TIME) or not ServerPool.get_instance().thread.is_alive():
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
