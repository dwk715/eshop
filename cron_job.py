#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/6/13 上午10:20
# @Author  : Dlala
# @File    : cron_job.py

from apscheduler.schedulers.background import BackgroundScheduler
from pymongo import MongoClient
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor

# mongodb 设置
mg_client = MongoClient(host='172.105.216.212',
                        port=27017,
                        username='dwk715',
                        password='lunxian715',
                        authSource='eshop_price')
db = mg_client['eshop_price']

