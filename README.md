shadowsocks manyuser branch
===========
Which people need this branch
------------------
1.share shadowsocks server

2.create multi server by shadowsocks

3.manage server (transfer / account)

Change
-------
从efd106dfb5这个提交开始能够独立于前端运行了，原因在于考虑到udp的话可靠性不好。在数据库中修改passwd，switch，enable，流量都会立即生效(比如改密码不需要再通过Managesocket去手动stop某个服务了)。不过内部实现还是通过数据库线程发送一个udp包来触发的，因为数据库这个操作改成异步的会灰常灰常麻烦，所以千万不要在iptabls里面把udp全给堵死了。<del>我的线上环境变成了瘟都死所以这个没有时间和环境测试，对运行过程中出现服务崩溃，服务器冒烟不负任何责任。</del>发现有问题的话给我个提交？诶哟好累英语太拙计就写中文好了。

Install
-------
install MySQL 5.x.x

`pip install cymysql`

create a database named `shadowsocks`

import `shadowsocks.sql` into `shadowsocks`

edit Config.py
Example:

	#Config
	MYSQL_HOST = 'mdss.mengsky.net'
	MYSQL_PORT = 3306
	MYSQL_USER = 'ss'
	MYSQL_PASS = 'ss'
	MYSQL_DB = 'shadowsocks'

	MANAGE_PASS = 'ss233333333'
	#if you want manage in other server you should set this value to global ip
	MANAGE_BIND_IP = '127.0.0.1'
	#make sure this port is idle
	MANAGE_PORT = 23333

TestRun `cd shadowsocks` ` python server.py`

if no exception server will startup. you will see such like
Example:

	db start server at port [%s] pass [%s]

Database user table column
------------------
`passwd` server pass

`port` server port

`t` last keepalive time

`u` upload transfer

`d` download transer

`transfer_enable` if u + d > transfer_enable this server will be stop (db_transfer.py del_server_out_of_bound_safe)

Manage socket
------------------
Manage server work in UDP at `MANAGE_BIND_IP` `MANAGE_PORT`

use `MANAGE_PASS:port:passwd:0` to del a server at port `port`

use `MANAGE_PASS:port:passwd:1` to run a server at port `port` password is `passwd`

Python Eg:

	udpsock.sendto('MANAGE_PASS:65535:123456:1', (MANAGE_BIND_IP, MANAGE_PORT))
	
PHP Eg:

	$sock = socket_create(AF_INET, SOCK_DGRAM, SOL_UDP);
	$msg = 'MANAGE_PASS:65535:123456:1';
	$len = strlen($msg);
	socket_sendto($sock, $msg, $len, 0, MANAGE_BIND_IP, MANAGE_PORT);
	socket_close($sock);

NOTICE
------------------
If error such like `2014-09-18 09:02:37 ERROR    [Errno 24] Too many open files`

edit /etc/security/limits.conf

Add:

	*                soft    nofile          8192
	*                hard    nofile          65535


add `ulimit -n 8192` in your startup script before runing


shadowsocks
===========
shadowsocksR mu forked from breakwa11/shadowsocks

[![PyPI version]][PyPI]
[![Build Status]][Travis CI]
[![Coverage Status]][Coverage]

A fast tunnel proxy that helps you bypass firewalls.

Server
------

### Install

Debian / Ubuntu:

    apt-get install python-pip
    pip install shadowsocks

CentOS:

    yum install python-setuptools && easy_install pip
    pip install shadowsocks

Windows:

See [Install Server on Windows]

### Usage

    ssserver -p 443 -k password -m aes-256-cfb

To run in the background:

    sudo ssserver -p 443 -k password -m aes-256-cfb --user nobody -d start

To stop:

    sudo ssserver -d stop

To check the log:

    sudo less /var/log/shadowsocks.log

Check all the options via `-h`. You can also use a [Configuration] file
instead.

Client
------

* [Windows] / [OS X]
* [Android] / [iOS]
* [OpenWRT]

Use GUI clients on your local PC/phones. Check the README of your client
for more information.

Documentation
-------------

You can find all the documentation in the [Wiki].

License
-------

Copyright 2015 clowwindy

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.

Bugs and Issues
----------------

* [Troubleshooting]
* [Issue Tracker]
* [Mailing list]



[Android]:           https://github.com/shadowsocks/shadowsocks-android
[Build Status]:      https://travis-ci.org/falseen/shadowsocks.svg?branch=manyuser-travis
[Configuration]:     https://github.com/shadowsocks/shadowsocks/wiki/Configuration-via-Config-File
[Coverage Status]:   https://jenkins.shadowvpn.org/result/shadowsocks
[Coverage]:          https://jenkins.shadowvpn.org/job/Shadowsocks/ws/PYENV/py34/label/linux/htmlcov/index.html
[Debian sid]:        https://packages.debian.org/unstable/python/shadowsocks
[iOS]:               https://github.com/shadowsocks/shadowsocks-iOS/wiki/Help
[Issue Tracker]:     https://github.com/shadowsocks/shadowsocks/issues?state=open
[Install Server on Windows]: https://github.com/shadowsocks/shadowsocks/wiki/Install-Shadowsocks-Server-on-Windows
[Mailing list]:      https://groups.google.com/group/shadowsocks
[OpenWRT]:           https://github.com/shadowsocks/openwrt-shadowsocks
[OS X]:              https://github.com/shadowsocks/shadowsocks-iOS/wiki/Shadowsocks-for-OSX-Help
[PyPI]:              https://pypi.python.org/pypi/shadowsocks
[PyPI version]:      https://img.shields.io/pypi/v/shadowsocks.svg?style=flat
[Travis CI]:         https://travis-ci.org/falseen/shadowsocks
[Troubleshooting]:   https://github.com/shadowsocks/shadowsocks/wiki/Troubleshooting
[Wiki]:              https://github.com/shadowsocks/shadowsocks/wiki
[Windows]:           https://github.com/shadowsocks/shadowsocks-csharp
