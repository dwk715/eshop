#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/6/13 上午10:20
# @Author  : Dlala
# @File    : cron_job.py

from apscheduler.schedulers.background import BackgroundScheduler
from pymongo import MongoClient
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from init_db.init_am_db import getGamesAM
from init_db.init_eu_db import getGamesEU
from init_db.init_jp_db import getGamesJP
import time


# mongodb 设置
mg_client = MongoClient(host='172.105.216.212',
                        port=27017,
                        username='dwk715',
                        password='lunxian715',
                        authSource='eshop_price')



if __name__ == '__main__':
    job_stores = {
        'mongo': MongoDBJobStore(collection='cron_job', database='eshop_price'),
        'default': MemoryJobStore
    }

    executors = {
        'default': ThreadPoolExecutor(10),
        'processpool': ProcessPoolExecutor(3)
    }

    job_defaults = {
        'coalesce': False,
        'max_instances': 3
    }

    scheduler = BackgroundScheduler(job_stores=job_stores, executors=executors, job_defaults=job_defaults)
    scheduler.add_job(getGamesJP, 'interval', days=1, start_date='2018-6-13 16:32:00')
    scheduler.add_job(getGamesAM, 'interval', days=1, start_date='2018-6-13 01:00:00')
    scheduler.add_job(getGamesEU, 'interval', days=1, start_date='2018-6-13 02:00:00')

    try:
        scheduler.start()
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()