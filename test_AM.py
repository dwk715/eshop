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

# mongodb 设置
mg_client = MongoClient(host='172.105.216.212', port=27017, username='dwk715', password='lunxian715',
                        authSource='eshop_price')
db = mg_client['eshop_price']
game_collection = db['game']
name_collection = db['name']

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



def getNameByGoogle(query, region):
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

        if region == 'en' and fuzz.ratio(titles['en'], query) < 70:
            return {}
        if region == 'jp' and fuzz.ratio(titles['jp'], query) < 70:
            return {}
        return titles
    else:
        return {}

def getTitleByEuSearch(slug):
    params = {
        'fl': "title",
        'fq': 'system_type:nintendoswitch* AND product_code_txt:*',
        'q': slug,
        'rows': 9999,
        'sort': 'sorting_title asc',
        'start': 0,
        'wt': 'json',
    }
    res = requests.get(GET_GAMES_EU_URL, params=params)
    if res.json()['response']['numFound'] == 1:
        print(res.json()['response']['docs'][0]['title'])
    else:
        return None

def testGameAM(game_info):
    game_am = game.copy()
    on_sale = True if (datetime.datetime.strptime(game_info['release_date'],
                                                    "%b %d, %Y") <= datetime.datetime.now()) else False
    nsuid = game_info['nsuid'] if game_info.__contains__('nsuid') else None
    date_from = datetime.datetime.strptime(game_info['release_date'], "%b %d, %Y").strftime("%Y-%m-%d")
    slug = game_info['slug'] if 'nintendo-switch' in game_info['slug'] else game_info['slug'].replace('-switch', '')
    game_am = {
        "title": {'am': game_info['title']},
        "slug": slug,
        "nsuid": {'am': game_info['nsuid']} if game_info.__contains__('nsuid') else {},
        "img": game_info['front_box_art'],
        "excerpt": None,
        "date_from": {'am': date_from},
        "on_sale": on_sale,
        "categories": [x.lower() for x in game_info['categories']['category']] if type(
            game_info['categories']['category']) is list else game_info['categories']['category'],
        "language_availability": [],
        "region": ['am'],
        "publisher": None,
        "google_titles": getNameByGoogle(game_info['title'], 'en')
    }


    if game_collection.find(
            {"$and": [{'title.eu': game_info['title']}, {'region': {"$nin": ["am"]}}]}).count() == 1:
            print('title')
            game_collection.update({'title': game_info['title']},
                                {"$set": {"title.am": game_info['title'],
                                        "nsuid.am": nsuid,
                                        "date_from.am": date_from,
                                        "region": ["eu", "am"]}})

    elif game_collection.find({"$and": [{'slug': slug}, {'region': {"$nin": ["am"]}}]}).count() == 1:
        print('slug')
        game_collection.update({'slug': slug},
                                {"$set": {"title.am": game_info['title'],
                                        "nsuid.am": nsuid,
                                        "date_from.am": date_from,
                                        "region": ["eu", "am"]}})

    elif game_am["google_titles"].__contains__('en') and game_collection.find({"$and": [
        {"google_titles.en": game_am["google_titles"]['en']}, {'region': {"$nin": ["am"]}}]}).count() == 1:
        print('google_titles')
        game_collection.update({"google_titles.en": game_am["google_titles"]['en']},
                                {"$set": {"title.am": game_info['title'],
                                        "nsuid.am": nsuid,
                                        "date_from.am": date_from,
                                        "region": ["eu", "am"]}})

    # 更新
    elif game_collection.find({'title.am': {'$regex':game_info['title'],'$options':'i'}}).count() == 1:
        print('update')
        game_collection.update({'title.am': {'$regex':game_info['title'],'$options':'i'}},{"$set": {"nsuid.am": nsuid,
                                            "on_sale": on_sale}})
        #更新 

    else:
        print('insert')
        game_collection.insert(game_am)

def main():
    getTitleByEuSearch('yodanji')
#     # name_list_EU = []
#     # print(len(list(game_collection.find({}))))
#     # for game_info in list(game_collection.find({})):
#     #     if game_info['title'].__contains__('eu'):
#     #         print(game_info['title']['eu'] )
#     #     # name_list_EU.append(game_info['title']['EU'])
#
#     game_info = {
# "categories": {
# "category": [
# "Role-Playing",
# "Strategy",
# "Adventure",
# "Simulation"
# ]
# },
# "slug": "yodanji-switch",
# "buyitnow": "false",
# "release_date": "Dec 7, 2017",
# "digitaldownload": "false",
# "free_to_start": "false",
# "title": "Y&#333;danji",
# "system": "Nintendo Switch",
# "id": "d-2NA4uGiqo7W9BLk-OsYYoTqw6gmWUq",
# "ca_price": "6.99",
# "number_of_players": "1 player",
# "nsuid": "70010000001564",
# "eshop_price": "4.99",
# "front_box_art": "https://media.nintendo.com/nintendo/bin/bEvVz5xeRLFGym1BvP5AM9-1G5xlVYdc/EMIbpArVpRPi3sHCfEqsvjoz7lj1Hs7h.png",
# "game_code": "HACNAGS7A",
# "buyonline": "true"
# }
    # testGameAM(game_info)
    # getNameByEuSearch('yodanji')

if __name__ == '__main__':
    main()