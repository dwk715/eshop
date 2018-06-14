#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/6/13 上午10:20
# @Author  : Dlala
# @File    : cron_job.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from init_db.init_am_db import getGamesAM
from init_db.init_eu_db import getGamesEU
from init_db.init_jp_db import getGamesJP
import time
import logging
import datetime

# 日志设置
today = datetime.datetime.now().strftime("%Y-%m-%d")  # 记录日志用
LOG_FORMAT = "%(asctime)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d"
log_file = 'log/' + today + '.log'
logging.basicConfig(filename=log_file, level=logging.DEBUG, format=LOG_FORMAT, datefmt=DATE_FORMAT)


if __name__ == '__main__':


    executors = {
        'default': ThreadPoolExecutor(10),
        'processpool': ProcessPoolExecutor(3)
    }

    job_defaults = {
        'coalesce': False,
        'max_instances': 3
    }

    scheduler = BackgroundScheduler(job_stores=MemoryJobStore, executors=executors, job_defaults=job_defaults)
    scheduler.add_job(getGamesJP, 'interval', days=1, start_date='2018-6-15 00:00:00')
    scheduler.add_job(getGamesAM, 'interval', days=1, start_date='2018-6-15 01:00:00')
    scheduler.add_job(getGamesEU, 'interval', days=1, start_date='2018-6-15 02:00:00')

    scheduler.start()

    try:

        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()