#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/6/5 下午1:32
# @Author  : Dlala
# @File    : init_am_db.py

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
from fuzzywuzzy import process
import html


# URL
GET_GAMES_AM_URL = "http://www.nintendo.com/json/content/get/filter/game?system=switch"
GET_GAMES_EU_URL = "http://search.nintendo-europe.com/en/select"
GET_GAMES_JP_SEARCH = "https://www.nintendo.co.jp/api/search/title?category=products&pf=switch&q="
GUESS_GAMES_GP_URL = 'https://ec.nintendo.com/JP/ja/titles/'
GET_PRICE_URL = "https://api.ec.nintendo.com/v1/price?lang=en"
GET_AC_GAMER_URL = "https://acg.gamer.com.tw/index.php?&p=NS"

# params 参数
GAME_LIST_LIMIT = 200
PRICE_LIST_LIMIT = 50

# 日服re
NSUID_REGEX_JP = r'\d{14}'
JSON_REGEX = r'NXSTORE\.titleDetail\.jsonData = ([^;]+);'

GAME_CHECK_CODE_US = 70010000000185
GAME_CHECK_CODE_EU = 70010000000184
GAME_CHECK_CODE_JP = 70010000000039
FIRST_NSUID = 70010000000026

REGION_ASIA = "CN HK AE AZ HK IN JP KR MY SA SG TR TW".split(' ')
REGION_EUROPE = "AD AL AT AU BA BE BG BW CH CY CZ DE DJ DK EE ER ES FI FR GB GG GI GR HR HU IE IM IS IT JE LI LS LT LU LV MC ME MK ML MR MT MZ NA NE NL NO NZ PL PT RO RS RU SD SE SI SK SM SO SZ TD VA ZA ZM ZW".split(
    ' ')
REGION_AMERICA = "AG AI AR AW BB BM BO BR BS BZ CA CL CO CR DM DO EC GD GF GP GT GY HN HT JM KN KY LC MQ MS MX NI PA PE PY SR SV TC TT US UY VC VE VG VI".split(
    ' ')

COUNTRIES = "AT AU BE BG CA CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IT JP LT LU LV MT MX NL NO NZ PL PT RO RU SE SI SK US ZA".split(
    ' ')

# 日志设置
today = datetime.datetime.now().strftime("%Y-%m-%d")  # 记录日志用
LOG_FORMAT = "%(asctime)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d"
log_file = 'log/' + today + '.log'
logging.basicConfig(filename=log_file, level=logging.ERROR, format=LOG_FORMAT, datefmt=DATE_FORMAT)

# mongodb 设置
mg_client = MongoClient(host='172.105.216.212',
                        port=27017,
                        username='dwk715',
                        password='lunxian715',
                        authSource='eshop_price')
db = mg_client['eshop_price']
game_am_collection = db['am_game']


# 数据库格式
game = {

    "title": None,  # title --> string 游戏名称

    'slug': None,  # slug --> str 名称代'-' 用于连接美服和欧服的游戏

    "nsuid": None,  # nsuid --> str 游戏ID,不同服务器同一游戏不同nsuid,根据nsuid查询价格

    "img": None,  # img --> str(url) 图片，欧服为正方形图片，美服为商品图片，可能是正方形，可能是长方形

    "excerpt": None,  # excerpt --> str 游戏描述

    "date_from": None,  # date_from --> str 游戏发售日，游戏发售日各个服务器可能不相同

    "on_sale": False,  # on_sale --> bool 根据游戏发售日判断有无在售卖

    "publisher": None,  # publisher --> str 发行商，前端暂时不作展示

    "categories": [],  # categories --> [] 游戏分类,可用于前端分类使用

    "region": 'am',  # region --> []归属地

    "language_availability": [],  # language_availability --> [] 支持的语言，美服无法获取数据，只取欧服和日服

    "google_titles": {}  # google_titles --> {} 使用google Knowledge Graph Search API 搜索 name 做合并用

}

# 使用Google API获取游戏名称
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

        if region == 'en' and fuzz._token_sort(titles['en'].lower(), query.lower(), partial=False,
                                               full_process=True) < 70:
            return {}
        if region == 'jp' and fuzz._token_sort(titles['ja'], query, partial=False, full_process=True) < 70:
            return {}
        return titles
    else:
        return {}

# 美服DB录入
def getAMGameOffeset(times):
    params = {
        'offset': 200 * times,
        'limit': 200
    }
    try:
        res = requests.get(GET_GAMES_AM_URL, params=params)

        result = res.json()['games']['game']
        return result
    except TimeoutError:
        logging.error("get America games info timeout")
        return []
    except Exception as error:
        logging.error("America error: {}".format(error))


# 获取美服数据
def getGamesAM():
    params = {
        'offset': 0,
        'limit': 200
    }
    try:
        res = requests.get(GET_GAMES_AM_URL, params=params)
        res.encoding = 'utf-8'
        total = int(res.json()['filter']['total'])  # 美服游戏总数
    except TimeoutError:
        logging.error("get America games info timeout")
        return None
    except Exception as error:
        logging.error("America error: {}".format(error))
        return None

    offset_times = int(math.ceil(total / 200))
    result = []

    for i in range(offset_times):
        result = result + getAMGameOffeset(i)

    print('AM games: ', len(result))

    for game_info in result:
        title = html.unescape(game_info['title'])
        on_sale = True if (datetime.datetime.strptime(game_info['release_date'],
                                                      "%b %d, %Y") <= datetime.datetime.now()) else False
        nsuid = game_info['nsuid'] if game_info.__contains__('nsuid') else None
        date_from = datetime.datetime.strptime(game_info['release_date'], "%b %d, %Y").strftime("%Y-%m-%d")
        slug = game_info['slug'] if 'nintendo-switch' in game_info['slug'] else game_info['slug'].replace('-switch', '')
        game_am = game.copy()
        game_am = {
            "title": title,
            "slug": slug,
            "nsuid": game_info['nsuid'] if game_info.__contains__('nsuid') else {},
            "img": game_info['front_box_art'],
            "excerpt": None,
            "date_from": date_from,
            "on_sale": on_sale,
            "categories": [x.lower() for x in game_info['categories']['category']] if type(
                game_info['categories']['category']) is list else game_info['categories']['category'],
            "language_availability": {},
            "region": 'am',
            "publisher": None,
            "google_titles": getTitleByGoogle(title, 'en')
        }
        # 判断有无记录
        if game_am_collection.find({'slug': slug}).count() != 0:
            game_am_collection.find_one_and_update({'slug': slug}, {
                "$set": {"title": title,"nsuid": nsuid, "date_from": date_from, "on_sale": on_sale}})
        else:
            game_am_collection.insert(game_am)

if __name__ == '__main__':
    getGamesAM()