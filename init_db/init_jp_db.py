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
import copy

GUESS_GAMES_GP_URL = 'https://ec.nintendo.com/JP/ja/titles/'
GET_PRICE_URL = "https://api.ec.nintendo.com/v1/price?lang=en"

NSUID_REGEX_JP = r'\d{14}'
JSON_REGEX = r'NXSTORE\.titleDetail\.jsonData = ([^;]+);'

FIRST_NSUID = 70010000000026

# 日志设置
today = datetime.datetime.now().strftime("%Y-%m-%d")  # 记录日志用
LOG_FORMAT = "%(asctime)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d"
log_file = 'eshop/log/' + today + '.log'
logging.basicConfig(filename=log_file, level=logging.ERROR, format=LOG_FORMAT, datefmt=DATE_FORMAT)

# mongodb 设置
mg_client = MongoClient(host='172.105.216.212', port=27017, username='dwk715', password='lunxian715',
                        authSource='eshop_price')
db = mg_client['eshop_price']
game_jp_collection = db['jp_game']
name_collection = db['name']

# 定义数据库格式
game_info = {

    "title": {},  # title --> string 游戏名称

    'slug': None,  # slug --> str 名称代'-' 用于连接美服和欧服的游戏

    "nsuid": None,  # nsuid --> list[] 游戏ID,不同服务器同一游戏不同nsuid,根据nsuid查询价格

    "img": None,  # img --> str(url) 图片，欧服为正方形图片，美服为商品图片，可能是正方形，可能是长方形

    "excerpt": None,  # excerpt --> str 游戏描述

    "date_from": str,  # date_from --> {} 游戏发售日，游戏发售日各个服务器可能不相同

    "on_sale": False,  # on_sale --> bool 根据游戏发售日判断有无在售卖

    "publisher": None,  # publisher --> str 发行商，前端暂时不作展示

    "categories": [],  # categories --> [] 游戏分类,可用于前端分类使用

    "region": [],  # region --> []归属地

    "language_availability": {},  # language_availability --> {} 支持的语言，美服无法获取数据，只取欧服和日服

    "google_titles": {},  # google_titles --> {} 使用google Knowledge Graph Search API 搜索 name 做合并用

    "prices": {}  # 日服价格

}


def getTitleByGoogle(query, region):
    api_key = "AIzaSyBW2n_2ZD7q-anVs2UL_WA8xESG7uqokdw"
    service_url = 'https://kgsearch.googleapis.com/v1/entities:search'
    if 'アケアカNEOGEO' in query:
        query = query.split('アケアカNEOGEO ')[0]
    if 'アーケードアーカイブス' in query:
        query = query.split('アーケードアーカイブス ')[0]
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

            title = html.unescape(game['formal_name'])

            nsuid = int(game['id'])
            try:
                img = game['applications'][0]['image_url']
            except:
                img = BeautifulSoup(r.text, features='lxml').find('meta', {'property': "twitter:image:src"}).attrs[
                    'content']
            excerpt = game['description']
            date_from = game['release_date_on_eshop']
            try:
                on_sale = True if (datetime.datetime.strptime(game['release_date_on_eshop'],
                                                              "%Y-%m-%d") <= datetime.datetime.now()) else False
            except ValueError:
                on_sale = False

            publisher = game['publisher']['name']
            language_availability = [
                iso639.to_name(i['iso_code']).lower().split(';')[0] if ';' in iso639.to_name(
                    i['iso_code']).lower() else iso639.to_name(i['iso_code']).lower() for i in game['languages']]

            game_jp = copy.deepcopy(game_info)

            game_jp.update({
                "title": title,
                "nsuid": nsuid,
                "img": img,
                "excerpt": excerpt,
                "date_from": date_from,
                "on_sale": on_sale,
                "publisher": publisher,
                "region": ['jp'],
                "language_availability": language_availability,
                "google_titles": getTitleByGoogle(title, 'jp')
            })
            currency, price, jp_discount = getPrice(nsuid)
            if jp_discount == None:
                game_jp.update({
                    "prices": {"JP": {currency: price,
                                      }}

                })
            else:
                game_jp.update({
                    "prices": {"JP": {currency: price,
                                      "discount": jp_discount
                                      }}

                })
            game_jp_collection.find_one_and_update({'title': title}, {"$set": game_jp}, upsert=True)


def getPrice(nsuid):
    params = {
        'country': "JP",
        'ids': nsuid,
    }
    response = requests.get(url=GET_PRICE_URL, params=params).json()
    if response['prices'][0].__contains__('discount_price'):
        discount_price = float(response['prices'][0]['discount_price']['raw_value'])
        regular_price = float(response['prices'][0]['regular_price']['raw_value'])
        jp_discount = '%.f%%' % (discount_price / regular_price * 100)
        currency = response['prices'][0]['discount_price']['currency']

        return currency, discount_price, jp_discount

    elif response['prices'][0].__contains__('regular_price'):
        regular_price = float(response['prices'][0]['regular_price']['raw_value'])
        currency = response['prices'][0]['regular_price']['currency']
        jp_discount = None
        return currency, regular_price, jp_discount
    else:
        print(nsuid)


def getNameByFuzzSearch(title):
    fuzz_ratios = {}
    for game_info in list(game_jp_collection.find()):
        fuzz_ratios[game_info['title']] = fuzz._token_sort(title, game_info['title'], partial=False, full_process=True)
    result = max(fuzz_ratios.items(), key=lambda x: x[1])
    if result[1] > 70:
        return result[0]
    return False


def addAcNamesToJPNameDB():
    a = 0
    b = c = d = a
    for names in list(name_collection.find()):
        if names['jp_name'] != "":
            if game_jp_collection.find({'title': {"$regex": names['jp_name'], "$options": "i"}}).count() == 1:
                game_jp_collection.find_one_and_update({'title': {"$regex": names['jp_name'], "$options": "i"}},
                                                       {"$set": {"ac_names": names}})
                a += 1
            elif getNameByFuzzSearch(names['jp_name']):
                game_jp_collection.find_one_and_update({'title': getNameByFuzzSearch(names["jp_name"])},
                                                       {"$set": {"ac_names": names}})
                b += 1
        if names['eu_name'] != "":
            if game_jp_collection.find({'title': {"$regex": names['eu_name'], "$options": "i"}}).count() == 1:
                game_jp_collection.find_one_and_update({'title': {"$regex": names['eu_name'], "$options": "i"}},
                                                       {"$set": {"ac_names": names}})
                c += 1
            elif getNameByFuzzSearch(names['eu_name']):
                game_jp_collection.find_one_and_update({'title': getNameByFuzzSearch(names["eu_name"])},
                                                       {"$set": {"ac_names": names}})
                d += 1
    print(a)
    print(b)
    print(c)
    print(d)


if __name__ == '__main__':
    getGamesJP()
    # addAcNamesToJPNameDB()
