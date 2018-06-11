#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/6/5 下午1:32
# @Author  : Dlala
# @File    : init_eu_db.py

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
import copy

# URL
GET_GAMES_EU_URL = "http://search.nintendo-europe.com/en/select"
GET_PRICE_URL = "https://api.ec.nintendo.com/v1/price?lang=en"

# params 参数
GAME_LIST_LIMIT = 200
PRICE_LIST_LIMIT = 50

REGION_EUROPE = "AT NL FR CZ DK DE ES FI GR HU IT NO PL PT RU ZA SE UK AU NZ".split(' ')

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
game_collection = db['game']
name_collection = db['name']
game_eu_collection = db['eu_game']

# 数据库格式
game = {

    "title": None,  # title --> string 游戏名称

    'slug': None,  # slug --> str 名称代'-' 用于连接美服和欧服的游戏

    "nsuid": None,  # nsuid --> list[] 游戏ID,不同服务器同一游戏不同nsuid,根据nsuid查询价格

    "img": None,  # img --> str(url) 图片，欧服为正方形图片，美服为商品图片，可能是正方形，可能是长方形

    "excerpt": None,  # excerpt --> str 游戏描述

    "date_from": None,  # date_from --> {} 游戏发售日，游戏发售日各个服务器可能不相同

    "on_sale": False,  # on_sale --> bool 根据游戏发售日判断有无在售卖

    "publisher": None,  # publisher --> str 发行商，前端暂时不作展示

    "categories": [],  # categories --> [] 游戏分类,可用于前端分类使用

    "region": 'eu',  # region --> []归属地

    "language_availability": [],  # language_availability --> {} 支持的语言，美服无法获取数据，只取欧服和日服

    "google_titles": {},  # google_titles --> {} 使用google Knowledge Graph Search API 搜索 name 做合并用

    "eu_discount": None,  # 欧服折扣

    "prices": {}  # 欧区价格

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


def getGamesEU():
    params = {
        'fl': "title, nsuid_txt, product_code_txt, date_from, image_url_sq_s, publisher, excerpt, game_categories_txt, language_availability, url",
        'fq': 'system_type:nintendoswitch* AND product_code_txt:*',
        'q': '*',
        'rows': 9999,
        'sort': 'sorting_title asc',
        'start': 0,
        'wt': 'json',
    }
    try:
        res = requests.get(GET_GAMES_EU_URL, params=params)
        result = res.json()['response']['docs']
    except TimeoutError:
        logging.error("get Europe games info timeout")
        return None
    except Exception as error:
        logging.error("Europe error: {}".format(error))
        return None

    for game_info in result:
        title = game_info['title']
        date_from = game_info['date_from'].split('T')[0]
        on_sale = True if (datetime.datetime.strptime(game_info['date_from'].split('T')[0],
                                                      "%Y-%m-%d") <= datetime.datetime.now()) else False
        slug = ('-').join([x.lower() for x in game_info['url'].split('/')[-1].split('-')[:-1] if len(x) > 0])
        nsuid = game_info['nsuid_txt'][0] if game_info.__contains__('nsuid_txt') else None
        publisher = game_info['publisher'] if game_info.__contains__('publisher') else None
        game_eu = copy.deepcopy(game)
        game_eu.update(
            {
                "title": title,
                "slug": slug,
                "nsuid": nsuid,
                "img": game_info['image_url_sq_s'],
                "excerpt": game_info['excerpt'],
                "date_from": game_info['date_from'].split('T')[0],
                "on_sale": on_sale,
                "categories": game_info['game_categories_txt'],
                "language_availability": game_info['language_availability'][0].split(','),
                "region": 'eu',
                "publisher": publisher,
                "google_titles": getTitleByGoogle(title, 'en')
            }
        )
        # 判断有无记录
        game_eu_collection.find_one_and_update({"slug": slug}, {"$set": game_eu}, upsert=True)





def getPrice():
    for country in REGION_EUROPE:
        offset = 0
        nsuids = []
        for game_info in game_eu_collection.find({'nsuid': {"$type": 2}}):
            nsuids.append(game_info['nsuid'])
        while (offset < len(nsuids)):
            params = {
                'country': country,
                'ids': nsuids[offset: offset + PRICE_LIST_LIMIT]
            }
            offset += PRICE_LIST_LIMIT
            response = requests.get(url=GET_PRICE_URL, params=params).json()
            for price in response['prices']:
                if price.__contains__('discount_price'):
                    discount_price = float(price['discount_price']['raw_value'])
                    regular_price = float(price['regular_price']['raw_value'])
                    am_discount = '%.f%%' % (discount_price / regular_price * 100)
                    currency = price['discount_price']['currency']
                    game_eu_collection.find_one_and_update({'nsuid': str(price['title_id'])}, {"$set": {
                        "am_discount": am_discount,
                        "prices": {currency: discount_price}
                    }})
                elif price.__contains__('regular_price'):
                    regular_price = float(price['regular_price']['raw_value'])
                    currency = price['regular_price']['currency']
                    game_eu_collection.find_one_and_update({'nsuid': str(price['title_id'])}, {"$set": {
                        "prices": {currency: regular_price}
                    }})
                else:
                    continue


if __name__ == '__main__':
    # getGamesEU()
    getPrice()
