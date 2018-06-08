#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/5/15 上午9:41
# @Author  : Dlala
# @File    : test_api.py
"""Example of Python client calling Knowledge Graph Search API."""
import json
import urllib.request
import urllib.parse
import requests

api_key = "AIzaSyBW2n_2ZD7q-anVs2UL_WA8xESG7uqokdw"
query = "THE KING OF FIGHTERS 2000"
service_url = 'https://kgsearch.googleapis.com/v1/entities:search'
params = {
    'query': query,
    'limit': 10,
    'indent': True,
    'key': api_key,
}
# url = service_url + '?' + urllib.parse.urlencode(params)
# response = json.loads(urllib.request.urlopen(url).read())
response = requests.get(service_url, params=params)
print(response.json())