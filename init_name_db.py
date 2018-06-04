#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/5/2 上午10:45
# @Author  : Dlala
# @File    : init_name_db.py
# 更新间隔每周一次

from pymongo import MongoClient
from opencc import OpenCC
import requests
from bs4 import BeautifulSoup
import gevent
from tqdm import tqdm
from gevent import monkey, pool
monkey.patch_all();

GET_AC_GAMER_URL = "https://acg.gamer.com.tw/acgDetail.php?"

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


def getNamesByAcGamer():
    # jobs = [gevent.spawn(dataCleaning, id) for id in range(85000, 99999)]
    # gevent.joinall(jobs)
    for id in tqdm(range(85000, 99999)):
        dataCleaning(id)



def dataCleaning(id):
    openCC = OpenCC('tw2s')
    params = {
        's': id
    }
    try:
        r = requests.get(GET_AC_GAMER_URL, timeout= 100 ,params=params)
    except TimeoutError:
        return None
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, features='lxml')
    platform = soup.find('a', {'class': 'link2'})
    if not platform:
        return None
    if platform.text == 'Nintendo Switch ( NS )':
        tw_name = soup.find('h1').text
        cn_name = openCC.convert(str(tw_name))
        jp_name = soup.find_all('h2')[0].text
        eu_name = soup.find_all('h2')[1].text

        names = {
            'tw_name': tw_name,
            'cn_name': cn_name,
            'jp_name': jp_name,
            'eu_name': eu_name
        }
        name_collection.update({'tw_name': tw_name}, names, upsert=True)

    return None

def testNsuid():
    for game in game_collection.find({"$and": [{"region": ["eu", "am"]}, {"title.jp": {"$exists": False}}]}):
        # print(game)
        try:
            if int(game["nsuid"]['am']) - int(game["nsuid"]['eu']) == 1 and game_jp_collection.find(
                    {"nsuid": str(int(game["nsuid"]["am"]) + 1)}).count() == 1:
                print(game["title"])
                print(game_jp_collection.find_one({"nsuid": str(int(game["nsuid"]["am"]) + 1)})['title'])
                print('插入吗？y or n \n')
                choice = input()
                if choice == 'y':
                    game_all = game['title'].copy()
                    game_all['jp'] = game_jp_collection.find_one({"nsuid": str(int(game["nsuid"]["am"]) + 1)})['title']
                    name_collection.insert(game_all)
                else:
                    continue
        except:
            continue
def changeNameBD():
    for name in name_collection.find():
        if name.__contains__('am'):
            name_collection.find_one_and_update({'am': name['am']},
                                                {"$set":{"eu_name": name['am'],
                                                         "jp_name": name['jp']}})

if __name__ == '__main__':
    # getNamesByAcGamer()
    # testNsuid()
    changeNameBD()

