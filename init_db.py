#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/5/25 上午10:23
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
import iso639
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import html

# URL
GET_GAMES_US_URL = "http://www.nintendo.com/json/content/get/filter/game?system=switch"
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
game_collection = db['game']
name_collection = db['name']
game_jp_collection = db['jp_game']

# 数据库格式
game = {

    "title": {},  # title --> string 游戏名称

    'slug': None,  # slug --> str 名称代'-' 用于连接美服和欧服的游戏

    "nsuid": {},  # nsuid --> list[] 游戏ID,不同服务器同一游戏不同nsuid,根据nsuid查询价格

    "img": None,  # img --> str(url) 图片，欧服为正方形图片，美服为商品图片，可能是正方形，可能是长方形

    "excerpt": None,  # excerpt --> str 游戏描述

    "date_from": {},  # date_from --> {} 游戏发售日，游戏发售日各个服务器可能不相同

    "on_sale": {},  # on_sale --> bool 根据游戏发售日判断有无在售卖

    "publisher": None,  # publisher --> str 发行商，前端暂时不作展示

    "categories": [],  # categories --> [] 游戏分类,可用于前端分类使用

    "region": [],  # region --> []归属地

    "language_availability": {},  # language_availability --> {} 支持的语言，美服无法获取数据，只取欧服和日服

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

        if region == 'en' and fuzz._token_sort(titles['en'].lower(), query.lower(), partial=True,
                                               full_process=True) < 70:
            return {}
        if region == 'jp' and fuzz._token_sort(titles['ja'], query, partial=True, full_process=True) < 70:
            return {}
        return titles
    else:
        return {}


# 模糊查找
def getTitleByFuzzSearch(title):
    fuzz_ratios = {}
    for game_info in list(game_collection.find({'title.am': {"$exists": True}})):
        fuzz_ratios[game_info['title']['am']] = fuzz._token_sort(title, game_info['title']['am'], partial=True,
                                                                 full_process=True)
    result = max(fuzz_ratios.items(), key=lambda x: x[1])
    if result[1] > 70:
        return result[0]
    return False


# 美服DB写入
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
        'limit': 200
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

    print('AM games: ', len(result))

    for game_info in result:
        game_am = game.copy()
        title = html.unescape(game_info['title'])
        on_sale = True if (datetime.datetime.strptime(game_info['release_date'],
                                                      "%b %d, %Y") <= datetime.datetime.now()) else False
        nsuid = game_info['nsuid'] if game_info.__contains__('nsuid') else None
        date_from = datetime.datetime.strptime(game_info['release_date'], "%b %d, %Y").strftime("%Y-%m-%d")
        slug = game_info['slug'] if 'nintendo-switch' in game_info['slug'] else game_info['slug'].replace('-switch', '')
        game_am = {
            "title": {'am': title},
            "slug": slug,
            "nsuid": {'am': game_info['nsuid']} if game_info.__contains__('nsuid') else {},
            "img": game_info['front_box_art'],
            "excerpt": None,
            "date_from": {'am': date_from},
            "on_sale": {'am': on_sale},
            "categories": [x.lower() for x in game_info['categories']['category']] if type(
                game_info['categories']['category']) is list else game_info['categories']['category'],
            "language_availability": {},
            "region": ['am'],
            "publisher": None,
            "google_titles": getTitleByGoogle(title, 'en')
        }
        if game_collection.find({'title.am': title}).count() == 1:
            game_collection.find_one_and_update({'title.am': title}, {
                "$set": {"nsuid.am": nsuid, "date_from.am": date_from, "on_sale.am": on_sale}})
        else:
            game_collection.insert(game_am)


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
        title = game_info['title']
        date_from = game_info['date_from'].split('T')[0]
        on_sale = True if (datetime.datetime.strptime(game_info['date_from'].split('T')[0],
                                                      "%Y-%m-%d") <= datetime.datetime.now()) else False
        slug = ('-').join([x.lower() for x in game_info['url'].split('/')[-1].split('-')[:-1] if len(x) > 0])
        nsuid = game_info['nsuid_txt'][0] if game_info.__contains__('nsuid_txt') else None
        publisher = game_info['publisher'] if game_info.__contains__('publisher') else None
        game_eu.update(
            {
                "title": {'eu': title},
                "slug": slug,
                "nsuid": {'eu': nsuid},
                "img": game_info['image_url_sq_s'],
                "excerpt": game_info['excerpt'],
                "date_from": {'eu': game_info['date_from'].split('T')[0]},
                "on_sale": on_sale,
                "categories": game_info['game_categories_txt'],
                "language_availability": {'eu': game_info['language_availability'][0].split(',')},
                "region": ['eu'],
                "publisher": publisher,
                "google_titles": getTitleByGoogle(slug, 'en')
            }
        )

        # 根据title查找
        if game_collection.find({"title.am": {"$regex": title, "$options": "i"}}).count() == 1:
            print(1)
            game_collection.find_one_and_update({'title.am': {'$regex': title, '$options': 'i'}},
                                                {"$set": {"title.eu": title,
                                                          "nsuid.eu": nsuid,
                                                          "date_from.eu": date_from,
                                                          "publisher": publisher,
                                                          "language_availability": {
                                                              'eu': game_info['language_availability'][0].split(',')},
                                                          "region": ["eu", "am"]}})

        # slug 查找
        elif game_collection.find({"$and": [{"slug": {"$regex": slug}}, {"region": "am"}]}).count() == 1:
            print(2)
            game_collection.find_one_and_update({"slug": {"$regex": slug}},
                                                {"$set": {"title.eu": title,
                                                          "nsuid.eu": nsuid,
                                                          "date_from.eu": date_from,
                                                          "publisher": publisher,
                                                          "language_availability": {
                                                              'eu': game_info['language_availability'][0].split(',')},
                                                          "region": ["eu", "am"]}})


        # 模糊查找
        elif getTitleByFuzzSearch(title) and game_collection.find(
                {'title.am': getTitleByFuzzSearch(title)}).count() == 1:
            print(3)
            game_collection.find_one_and_update({'title.am': getTitleByFuzzSearch(title)},
                                                {"$set": {"title.eu": title,
                                                          "nsuid.eu": nsuid,
                                                          "date_from.eu": date_from,
                                                          "publisher": publisher,
                                                          "language_availability": {
                                                              'eu': game_info['language_availability'][0].split(',')},
                                                          "region": ["eu", "am"]}})


        # google API查找
        elif game_eu["google_titles"].__contains__('en') and game_collection.find(
                {"$and": [{"google_titles.en": game_eu["google_titles"]['en']}, {"region": "am"}]}).count() == 1:
            print(4)
            game_collection.find_one_and_update(
                {"$and": [{"google_titles.en": game_eu["google_titles"]['en']}, {"region": "am"}]},
                {"$set": {"title.eu": title,
                          "nsuid.eu": nsuid,
                          "date_from.eu": date_from,
                          "publisher": publisher,
                          "language_availability": {
                              'eu': game_info['language_availability'][0].split(',')},
                          "region": ["eu", "am"]}}
            )


        # 更新
        elif game_collection.find(
                {"$and": [{'title.eu': game_info['title']}, {'region': {"$nin": ["am"]}}]}).count() == 1:
            game_collection.find_one_and_update({'title.eu': game_info['title']}, {"$set": game_eu})
        # 更新
        elif game_collection.find({"$and": [{'title.eu': game_info['title']}, {'region': ['eu', 'am']}]}).count() == 1:
            game_collection.find_one_and_update({'title.eu': game_info['title']}, {"$set": {"nsuid.eu": nsuid,
                                                                                            "on_sale.eu": on_sale}})

        else:
            game_collection.insert(game_eu)


def getTitlesByAcGamer():
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
        names = geTitleByAcGamerUrl(i)
        tw_name = names.get('tw_name')
        if name_collection.find({'tw_name': tw_name}).count() == 1:
            pass
        else:
            name_collection.insert(names)


def geTitleByAcGamerUrl(url):
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


def getNameByFuzzSearch(title):
    fuzz_ratios = {}
    for game_info in list(game_collection.find()):
        if game_info['title'].__contains__('am'):
            fuzz_ratios[game_info['title']['am']] = fuzz._token_sort(title, game_info['title']['am'], partial=True,
                                                                     full_process=True)
        else:
            fuzz_ratios[game_info['title']['eu']] = fuzz._token_sort(title, game_info['title']['eu'], partial=True,
                                                                     full_process=True)
    result = max(fuzz_ratios.items(), key=lambda x: x[1])
    if result[1] > 70:
        return result[0]
    return False


def addAcNamesToGameDB():
    a = 0
    b = c = a
    for names in list(name_collection.find()):
        if names['eu_name'] != "":
            if game_collection.find({'title.eu': {"$regex": names['eu_name'], "$options": 'i'}}).count() == 1:
                game_collection.find_one_and_update({'title.eu': {"$regex": names['eu_name'], "$options": 'i'}},
                                                    {"$set": {"ac_names": names}})
                a += 1
            elif game_collection.find({'title.am': {"$regex": names['eu_name'], "$options": 'i'}}) == 1:
                game_collection.find_one_and_update({'title.am': {"$regex": names['eu_name'], "$options": 'i'}},
                                                    {"$set": {"ac_names": names}})
                b += 1
            elif getNameByFuzzSearch(names['eu_name']):
                game_collection.find_one_and_update({'title.eu': getTitleByFuzzSearch(names['eu_name'])},
                                                    {"$set": {"ac_names": names}})
                game_collection.find_one_and_update({'title.am': getTitleByFuzzSearch(names['eu_name'])},
                                                    {"$set": {"ac_names": names}})
                c += 1


def linkJPGameAndGame():
    a = 0
    b = c = d = a
    for game_jp in game_jp_collection.find():
        #  直接美服名称对应
        if game_collection.find({'title.am': {"$regex": game_jp["title"], "$options": "i"}}).count() == 1:
            game_collection.find_one_and_update({'title.am': {"$regex": game_jp["title"], "$options": "i"}}, {
                "$set": {"title.jp": game_jp['title'],
                         "language_availability.jp": game_jp['language_availability']['jp'],
                         "nsuid.jp": game_jp['nsuid'],
                         "on_sale.jp": game_jp["on_sale"]}})
            a += 1
        # ACname对应
        elif game_jp.__contains__('ac_names') and game_collection.find(
                {"ac_names._id": game_jp['ac_names']['_id']}).count() == 1:
            game_collection.find_one_and_update({"ac_names._id": game_jp['ac_names']['_id']}, {
                "$set": {"title.jp": game_jp['title'],
                         "language_availability.jp": game_jp['language_availability']['jp'],
                         "nsuid.jp": game_jp['nsuid'],
                         "on_sale.jp": game_jp["on_sale"]}})
            b += 1
        # google_titles对应
        elif game_collection.find({"google_titles": game_jp["google_titles"]}).count() == 1:
            game_collection.find_one_and_update({"google_titles": game_jp["google_titles"]}, {
                "$set": {"title.jp": game_jp['title'],
                         "language_availability.jp": game_jp['language_availability']['jp'],
                         "nsuid.jp": game_jp['nsuid'],
                         "on_sale.jp": game_jp["on_sale"]}})
            c += 1

    print(a)
    print(b)
    print(c)
    print(d)


def testNsuid():
    for game in game_collection.find({"$and": [{"region": ["eu", "am"]}, {"title.jp": {"$exists": False}}]}):
        # print(game)
        try:
            if int(game["nsuid"]['am']) - int(game["nsuid"]['eu']) == 1 and game_jp_collection.find(
                    {"nsuid": str(int(game["nsuid"]["am"]) + 1)}).count() == 1:
                print(game["title"])
                print(game_jp_collection.find_one({"nsuid": str(int(game["nsuid"]["am"]) + 1)})['title'])
                print('\n')
        except:
            continue


if __name__ == '__main__':
    getGamesAM()
    getGamesEU()
    getTitlesByAcGamer()
    addAcNamesToGameDB()
    # linkJPGameAndGame()
    # testNsuid()
