#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/5/23 下午11:09
# @Author  : Dlala
# @File    : init_jp_db.py

from pymongo import MongoClient
import requests
import datetime
import logging
import math
from bs4 import BeautifulSoup
from opencc import OpenCC
import simplejson as json
import re
import iso639
from fuzzywuzzy import fuzz
import html

GUESS_GAMES_GP_URL = 'https://ec.nintendo.com/JP/ja/titles/'

NSUID_REGEX_JP = r'\d{14}'
JSON_REGEX = r'NXSTORE\.titleDetail\.jsonData = ([^;]+);'

FIRST_NSUID = 70010000000026

# 日志设置
today = datetime.datetime.now().strftime("%Y-%m-%d")  # 记录日志用
LOG_FORMAT = "%(asctime)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d"
log_file = 'log/' + today + '.log'
logging.basicConfig(filename=log_file, level=logging.ERROR, format=LOG_FORMAT, datefmt=DATE_FORMAT)

# mongodb 设置
mg_client = MongoClient(host='172.105.216.212', port=27017, username='dwk715', password='lunxian715',
                        authSource='eshop_price')
db = mg_client['eshop_price']
game_jp_collection = db['jp_game']

# 定义数据库格式
game = {

    "title": {},  # title --> string 游戏名称

    'slug': None,  # slug --> str 名称代'-' 用于连接美服和欧服的游戏

    "nsuid": {},  # nsuid --> list[] 游戏ID,不同服务器同一游戏不同nsuid,根据nsuid查询价格

    "img": None,  # img --> str(url) 图片，欧服为正方形图片，美服为商品图片，可能是正方形，可能是长方形

    "excerpt": None,  # excerpt --> str 游戏描述

    "date_from": {},  # date_from --> {} 游戏发售日，游戏发售日各个服务器可能不相同

    "on_sale": False,  # on_sale --> bool 根据游戏发售日判断有无在售卖

    "publisher": None,  # publisher --> str 发行商，前端暂时不作展示

    "categories": [],  # categories --> [] 游戏分类,可用于前端分类使用

    "region": [],  # region --> []归属地

    "language_availability": {},  # language_availability --> {} 支持的语言，美服无法获取数据，只取欧服和日服

    "google_titles": {}  # google_titles --> {} 使用google Knowledge Graph Search API 搜索 name 做合并用

}


def getTitleByGoogle(query, region):
    api_key = "AIzaSyBW2n_2ZD7q-anVs2UL_WA8xESG7uqokdw"
    service_url = 'https://kgsearch.googleapis.com/v1/entities:search'
    if 'ACA NEOGEO' in query:
        query = query.split('ACA NEOGEO ')[1]
    if 'Arcade Archives ' in query:
        query = query.split('Arcade Archives ')[1]
    params = {
        'query': query,
        'limit': 10,
        'indent': True,
        'key': api_key,
        'languages': ['en', 'ja', 'zh']
    }
    titles = {
        'en': '',
        'ja': '',
        'zh': ''
    }
    response = requests.get(service_url, params=params)
    if response.json().get('itemListElement') and response.json()['itemListElement'][0]['result'].get('name'):
        name_list = response.json()['itemListElement'][0]['result']['name']
        for name in name_list:
            if name['@language'] == 'en':
                titles['en'] = name['@value']
            elif name['@language'] == 'ja':
                titles['ja'] = name['@value']
            elif name['@language'] == 'zh':
                titles['zh'] = name['@value']

        if region == 'en' and fuzz.ratio(titles['en'].lower(), query.lower()) < 70:
            return {}
        if region == 'jp' and fuzz.ratio(titles['ja'], query) < 70:
            return {}
        return titles
    else:
        return {}


def getGamesJP():
    games = []
    for i in range(FIRST_NSUID, FIRST_NSUID + 9999):
        r = requests.get(GUESS_GAMES_GP_URL + str(i))
        r.encoding = 'utf-8'
        if r.status_code == 200:
            game = json.loads(re.search(JSON_REGEX, r.text).group(1))
            if '（' in game['formal_name']:
                title = game['formal_name'].split('（')[0]
            elif '™' in game['formal_name']:
                title = game['formal_name'].replace('™', '')
                title = title.replace('®', ' ') if '®' in title else title
            elif 'アケアカNEOGEO' in game['formal_name']:
                title = game['formal_name'].replace('アケアカNEOGEO ', '')
            elif 'アーケードアーカイブス ' in game['formal_name']:
                title = game['formal_name'].replace('アーケードアーカイブス ', '')
            elif '(' in game['formal_name']:
                title = game['formal_name'].split('(')[0]
            else:
                title = game['formal_name']
            nsuid = game['id']
            img = game['applications'][0]['image_url']
            excerpt = game['description']
            date_from = {'jp': game['release_date_on_eshop']}
            on_sale = True if (datetime.datetime.strptime(game['release_date_on_eshop'],
                                                          "%Y-%m-%d") <= datetime.datetime.now()) else False
            publisher = game['publisher']['name']
            language_availability = [
                iso639.to_name(i['iso_code']).lower().split(';')[0] if ';' in iso639.to_name(
                    i['iso_code']).lower() else iso639.to_name(i['iso_code']).lower() for i in game['languages']]

            game_jp = game.copy()

            game_jp = {
                "title": html.unescape(title),
                "nsuid": nsuid,
                "img": img,
                "excerpt": excerpt,
                "date_from": date_from,
                "on_sale": on_sale,
                "publisher": publisher,
                "region": ['jp'],
                "language_availability": {'jp': language_availability},
                "google_titles": getTitleByGoogle(title, 'jp')
            }
            game_jp_collection.find_one_and_update({'title':title}, {"$set": game_jp}, upsert=True)

if __name__ == '__main__':
    getGamesJP()
