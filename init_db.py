#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/4/24 上午9:40
# @Author  : Dlala
# @File    : init_db.py
# 更新game数据库

from pymongo import MongoClient
import requests
import datetime
import logging
import math
from bs4 import BeautifulSoup
from opencc import OpenCC
import simplejson as json
import re

GET_GAMES_US_URL = "http://www.nintendo.com/json/content/get/filter/game?system=switch"
GET_GAMES_EU_URL = "http://search.nintendo-europe.com/en/select"
GET_GAMES_JP_SEARCH = "https://www.nintendo.co.jp/api/search/title?category=products&pf=switch&q="
GUESS_GAMES_GP_URL = 'https://ec.nintendo.com/JP/ja/titles/'
GET_PRICE_URL = "https://api.ec.nintendo.com/v1/price?lang=en"
GET_AC_GAMER_URL = "https://acg.gamer.com.tw/index.php?&p=NS"

GAME_LIST_LIMIT = 200
PRICE_LIST_LIMIT = 50

NSUID_REGEX_JP = r'\d{14}'
JSON_REGEX = r'NXSTORE\.titleDetail\.jsonData = ([^;]+);'

GAME_CHECK_CODE_US = 70010000000185
GAME_CHECK_CODE_EU = 70010000000184
GAME_CHECK_CODE_JP = 70010000000039

REGION_ASIA = "CN HK AE AZ HK IN JP KR MY SA SG TR TW".split(' ')
REGION_EUROPE = "AD AL AT AU BA BE BG BW CH CY CZ DE DJ DK EE ER ES FI FR GB GG GI GR HR HU IE IM IS IT JE LI LS LT LU LV MC ME MK ML MR MT MZ NA NE NL NO NZ PL PT RO RS RU SD SE SI SK SM SO SZ TD VA ZA ZM ZW".split(
    ' ')
REGION_AMERICA = "AG AI AR AW BB BM BO BR BS BZ CA CL CO CR DM DO EC GD GF GP GT GY HN HT JM KN KY LC MQ MS MX NI PA PE PY SR SV TC TT US UY VC VE VG VI".split(
    ' ')

COUNTRIES = "AT AU BE BG CA CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IT JP LT LU LV MT MX NL NO NZ PL PT RO RU SE SI SK US ZA".split(
    ' ')

FIRST_NSUID = 70010000000026

# 日志设置
today = datetime.datetime.now().strftime("%Y-%m-%d")  # 记录日志用
LOG_FORMAT = "%(asctime)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d"
log_file = 'log/' + today + '.log'
logging.basicConfig(filename=log_file, level=logging.ERROR, format=LOG_FORMAT, datefmt=DATE_FORMAT)

# mongodb 设置
mg_client = MongoClient('localhost', 27017)
db = mg_client['eshop_price']
game_collection = db['game']
name_collection = db['name']

# 定义数据库格式
game = {
    # title --> string 名称
    "title": None,
    # slug --> str 名称代'-' 用于连接美服和欧服的游戏
    'slug': None,
    # nsuid --> list[] 游戏ID,不同服务器同一游戏不同nsuid,根据nsuid查询价格
    "nsuid": {},
    # img --> str(url) 图片，欧服为正方形图片，美服为商品图片，可能是正方形，可能是长方形
    "img": None,
    # excerpt --> str 游戏描述
    "excerpt": None,
    # date_from --> {} 游戏发售日，游戏发售日各个服务器可能不相同
    "date_from": {},
    # on_sale --> bool 根据游戏发售日判断有无在售卖
    "on_sale": False,
    # publisher --> str 发行商，前端暂时不作展示
    "publisher": None,
    # categories --> [] 游戏分类,可用于前端分类使用
    "categories": [],
    # language_availability --> {} 支持的语言，美服无法获取数据，只取欧服和日服
    "language_availability": {}

}


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
        game_eu = game.copy()
        on_sale = True if (datetime.datetime.strptime(game_info['date_from'].split('T')[0],
                                                      "%Y-%m-%d") <= datetime.datetime.now()) else False
        slug = ('-').join([x.lower() for x in game_info['url'].split('/')[-1].split('-')[:-1] if len(x) > 0])
        game_eu.update(
            {
                "title": game_info['title'],
                "slug": slug,
                "nsuid": {'eu': game_info['nsuid_txt'][0]} if game_info.__contains__('nsuid_txt') else {},
                "img": game_info['image_url_sq_s'],
                "excerpt": game_info['excerpt'],
                "date_from": {'eu': game_info['date_from'].split('T')[0]},
                "on_sale": on_sale,
                "categories": game_info['game_categories_txt'],
                "language_availability": {'eu': game_info['language_availability'][0].split(',')},
                "region": ['europe'],
                "publisher": game_info['publisher'] if game_info.__contains__('publisher') else None
            }
        )
        # 无记录，插入
        if game_collection.find_one({'slug': slug}) is None:
            game_collection.insert_one(game_eu)
        # 有记录，更新
        else:
            game_collection.find_one_and_update({'slug': slug}, {'$set': game_eu})


def getAMGameOffeset(times):
    params = {
        'offset': 200 * times,
        'limit': 200
    }
    try:
        res = requests.get(GET_GAMES_US_URL, params=params)

        result = res.json()['games']['game']
        return result
    except TimeoutError:
        logging.error("get America games info timeout")
        return []
    except Exception as error:
        logging.error("America error: {}".format(error))


def getGamesAM():
    params = {
        'offset': 0,
        'limit': 9999
    }
    try:
        res = requests.get(GET_GAMES_US_URL, params=params)
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

    for game_info in result:
        game_am = game.copy()
        on_sale = True if (datetime.datetime.strptime(game_info['release_date'],
                                                      "%b %d, %Y") <= datetime.datetime.now()) else False
        nsuid = game_info['nsuid'] if game_info.__contains__('nsuid') else None
        date_from = datetime.datetime.strptime(game_info['release_date'], "%b %d, %Y").strftime("%Y-%m-%d")
        slug = game_info['slug'].replace('-switch', '')
        game_am = {
            "title": game_info['title'],
            "slug": slug,
            "nsuid": {'am': game_info['nsuid']} if game_info.__contains__('nsuid') else {},
            "img": game_info['front_box_art'],
            "excerpt": None,
            "date_from": {'am': date_from},
            "on_sale": on_sale,
            "categories": [x.lower() for x in game_info['categories']['category']] if type(
                game_info['categories']['category']) is list else game_info['categories']['category'],
            "language_availability": [],
            "region": ['america'],
            "publisher": None
        }


        if game_collection.find({"$and": [{'slug': slug}, {'region': 'europe'}]}).count() == 1 :
            game_collection.find_one_and_update({'slug': slug},
                                                {"$set": {"title": game_info['title'], "nsuid.am": nsuid,
                                                          "date_from.am": date_from},
                                                 "$push": {'region': 'america'}})
        # 捡漏
        elif game_collection.find({'title': game_info['title']}).count() == 1:
            game_collection.find_one_and_update({'title': game_info['title']},
                                                {"$set":{"nsuid.am": nsuid,
                                                          "date_from.am": date_from},
                                                 "$push": {'region': 'america'}})
        elif game_collection.find({'slug': slug}).count() == 0 or game_collection.find({'title': game_info['title']}).count() == 0:
            game_collection.insert_one(game_am)

        else:
            game_collection.find_one_and_update({'slug': slug}, {'$set': game_am})


def getTitleByAcGamer():
    params_available_now = {
        't': '1'
    }
    params_coming_soon = {
        't': '2'
    }
    urls_available_now = getUrlsByAcGamer(params_available_now)
    urls_coming_soon = getUrlsByAcGamer(params_coming_soon)
    urls = urls_available_now | urls_coming_soon

    for i in urls:
        names = getNamesByAcGamerUrl(i)
        tw_name = names.get('tw_name')
        name_collection.update({'tw_name': tw_name}, names, upsert=True)


def getNamesByAcGamerUrl(url):
    openCC = OpenCC('tw2s')
    url = 'https:' + url
    r = requests.get(url)
    r.encoding = 'utf-8'
    tw_name = BeautifulSoup(r.text, features='lxml').find('h1').text
    cn_name = openCC.convert(tw_name)
    jp_name = BeautifulSoup(r.text, features='lxml').find_all('h2')[0].text
    eu_name = BeautifulSoup(r.text, features='lxml').find_all('h2')[1].text
    return {
        'cn_name': cn_name,
        'tw_name': tw_name,
        'jp_name': jp_name,
        'eu_name': eu_name
    }


def getUrlsByAcGamer(params):
    urls = set()
    soup = BeautifulSoup(requests.get(GET_AC_GAMER_URL, params=params).text,
                         features='lxml')
    pages = int(
        math.ceil(float(soup.find('a', {'class': 'next'})['href'].split('=')[-1]) / 15)) + 1
    for i in range(1, pages):
        params.update({'page': i})
        soup_available_now = BeautifulSoup(requests.get(GET_AC_GAMER_URL, params=params).text,
                                           features='lxml')
        child = soup_available_now.find_all('h1', {'class': 'ACG-maintitle'})
        for c in child:
            urls.add(c.find('a', href=True)['href'])
    return urls

def getGamesJP():
    games = []
    for i in range(FIRST_NSUID, FIRST_NSUID + 1500):
        r = requests.get(GUESS_GAMES_GP_URL + str(i))
        if r.status_code == 200:
            game = json.loads(re.search(JSON_REGEX, r.text).group(1))



if __name__ == '__main__':
    getGamesEU()
    getGamesAM()
    getTitleByAcGamer()

