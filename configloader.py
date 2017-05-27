#!/usr/bin/python
# -*- coding: UTF-8 -*-
import importloader

g_config = None

def load_config():
	global g_config
	g_config = importloader.loads(['user_api_config','api_config'])

def get_config():
	return g_config

load_config()

