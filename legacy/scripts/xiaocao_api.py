import requests
import pandas as pd
import time
import random
import json

headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,en-GB;q=0.6',
    'content-type': 'application/json',
    'origin': 'https://www.topxlc.com',
    'priority': 'u=1, i',
    'referer': 'https://www.topxlc.com/',
    'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) ' +
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36',
}

max_retries = 5
min_sleep_time = 0.1
max_sleep_time = 0.7


def _post_with_retry(url, headers, json_data):
    retries = 0
    while retries < max_retries:
        random_sleep_time = random.uniform(min_sleep_time, max_sleep_time)
        time.sleep(random_sleep_time)
        try:
            print('Post to', url)
            response = requests.post(url, headers=headers, json=json_data)
            response.raise_for_status()  # 检查响应状态码
            if response.json()['result'] is None:
                print(f"Retry: {response.json()['msg']}")
                continue
            return response.json()
        except requests.exceptions.HTTPError as errh:
            print(f"HTTP Error: {errh}")
        except requests.exceptions.ConnectionError as errc:
            print(f"Error Connecting: {errc}")
        except requests.exceptions.Timeout as errt:
            print(f"Timeout Error: {errt}")
        except requests.exceptions.RequestException as err:
            print(f"OOps: Something Else: {err}")
        retries += 1
        if retries < max_retries:
            print(f"尝试重新发送请求... ({retries}/{max_retries})")
    return None


def get_code_list(date, groups=3):
    """
    get all code list by group 代码列表
    :param date: e.g. '2024-10-25'
    :param groups: 0 接力 12; 1 竞王 1097；2 红盘 348； 3 低吸  73 ；
    """
    json_data = {
        'params': {
            'groups': str(groups),
            'date': date,
        },
    }

    json_resp = _post_with_retry('https://p-xcapi.topxlc.com/stock/focus_xiao_cao_index/get_code_list',
                                 headers={'token': 'be7d64c2a53b71dc57ed8b91c7722182', **headers}, json_data=json_data)
    if json_resp is None:
        return None

    return json_resp['result']['data']


def get_block_category_rank(date, model=0):
    """
    get block category rank 板块大类
    :param date: e.g. '2024-10-25'
    :param model: 0 or 1；
    """
    json_data = {
        'params': {
            'date': date,
            'model': 0,
        },
    }
    json_resp = _post_with_retry('https://p-xcapi.topxlc.com/stock/xiao_cao_block_category_rank_v2',
                                 headers=headers, json_data=json_data)
    if json_resp is None:
        return None
    return json_resp['result']['localCategoryRankList']


def get_index(date, stock_list):
    """
    get xiao cao index 个股信息
    :param date: e.g. '2024-10-25'
    :param stock_list: list of codes
    """
    json_data = {
        'params': {
            'stockCodes': stock_list,
            'date': date,
        },
    }
    json_resp = _post_with_retry('https://p-xcapi.topxlc.com/stock/xiao_cao_index',
                                 headers=headers, json_data=json_data)
    if json_resp is None:
        return None

    return [{**v} for _, v in json_resp['result'].items()]


def get_index_with_check(date, stock_list, check_field=None):
    """
    get xiao cao index 个股信息，如果没加载完就返回None
    :param date: e.g. '2024-10-25'
    :param stock_list: list of codes
    :param check_field: e.g. 'xcjw' 检查该字段是否空
    """
    indices = get_index(date, stock_list)
    for index in indices:
        if index['isWeak'] is None:
            # not loaded, therefore not ready for all
            return None
        if check_field is not None and index[check_field] is None:
            return None
    return indices


def get_industry_block_rank(date, model=0):
    """
    get industry block rank 当日方向 短线重点
    :param date: e.g. '2024-10-25'
    :param model: 0 or 1；
    """
    json_data = {
        'params': {
            'date': date,
            'model': 0,
        },
    }
    json_resp = _post_with_retry('https://p-xcapi.topxlc.com/stock/xiao_cao_industry_block_rank',
                                 headers=headers, json_data=json_data)
    if json_resp is None:
        return None
    return [{'date': date, **v} for v in json_resp['result']]


def wait_for_a_while():
    random_sleep_time = random.uniform(0.1, 0.3)
    time.sleep(random_sleep_time)


def get_sorted_code_list(date):
    """
    获取竞王排序列表
    :param date:
    """
    json_data = {
        'params': {
            'queryType': 1,
            'sortId': 40,
            'sortType': 1,
            'type': 0,
            'date': date,
        },
    }
    json_resp = _post_with_retry('https://p-xcapi.topxlc.com/stock/sort',
                                 headers=headers, json_data=json_data)
    return json_resp['result']
