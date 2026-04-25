import requests
import pandas as pd
import time
import random
import json

# 板块大类 'indexType': 0, result.localCategoryRankList[0]

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

dates = [
    '2024-10-25', '2024-10-24', '2024-10-23', '2024-10-22', '2024-10-21', '2024-10-18', '2024-10-17',
    '2024-10-16', '2024-10-15', '2024-10-14', '2024-10-11', '2024-10-10', '2024-10-09', '2024-10-08',
    '2024-09-30', '2024-09-27', '2024-09-26', '2024-09-25', '2024-09-24', '2024-09-23', '2024-09-20',
    '2024-09-19', '2024-09-18', '2024-09-13', '2024-09-12', '2024-09-11', '2024-09-10', '2024-09-09',
    '2024-09-06', '2024-09-05', '2024-09-04', '2024-09-03', '2024-09-02', '2024-08-30', '2024-08-29',
    '2024-08-28', '2024-08-27', '2024-08-26', '2024-08-23', '2024-08-22', '2024-08-21', '2024-08-20',
    '2024-08-19', '2024-08-16', '2024-08-15', '2024-08-14', '2024-08-13', '2024-08-12', '2024-08-09',
    '2024-08-08', '2024-08-07', '2024-08-06', '2024-08-05', '2024-08-02', '2024-08-01', '2024-07-31',
    '2024-07-30', '2024-07-29', '2024-07-26', '2024-07-25', '2024-07-24', '2024-07-23', '2024-07-22',
    '2024-07-19', '2024-07-18', '2024-07-17', '2024-07-16', '2024-07-15', '2024-07-12', '2024-07-11',
    '2024-07-10', '2024-07-09', '2024-07-08', '2024-07-05', '2024-07-04', '2024-07-03', '2024-07-02',
    '2024-07-01', '2024-06-28', '2024-06-27', '2024-06-26', '2024-06-25', '2024-06-24', '2024-06-21',
    '2024-06-20', '2024-06-19', '2024-06-18', '2024-06-17', '2024-06-14', '2024-06-13', '2024-06-12',
    '2024-06-11', '2024-06-07', '2024-06-06', '2024-06-05', '2024-06-04', '2024-06-03', '2024-05-31',
    '2024-05-30', '2024-05-29', '2024-05-28', '2024-05-27', '2024-05-24', '2024-05-23', '2024-05-22',
    '2024-05-21', '2024-05-20', '2024-05-17', '2024-05-16', '2024-05-15', '2024-05-14', '2024-05-13'
]

stocks = pd.read_json('stocks.json')

max_retries = 3
min_sleep_time = 0.1
max_sleep_time = 0.7

content = []
globalContent = []
for current_date in dates:
    print(current_date)
    json_data = {
        'params': {
            'date': current_date,
            'model': 0,
        },
    }
    random_sleep_time = random.uniform(0.3, 2)
    time.sleep(random_sleep_time)
    retries = 0
    while retries < max_retries:
        random_sleep_time = random.uniform(min_sleep_time, max_sleep_time)
        time.sleep(random_sleep_time)
        try:
            response = requests.post('https://p-xcapi.topxlc.com/stock/xiao_cao_block_category_rank_v2',
                                     headers=headers, json=json_data)
            response.raise_for_status()  # 检查响应状态码
            content.extend(response.json()['result']['localCategoryRankList'])
            globalContent.extend(response.json()['result']['globalCategoryRankList'])
            break  # 如果请求成功，跳出重试循环
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

with open('results/xiaocao_industry_block_category_rank_all_local_0.json', 'w') as f:
    json.dump(content, f, indent=4)

with open('results/xiaocao_industry_block_category_rank_all_global_0.json', 'w') as f:
    json.dump(globalContent, f, indent=4)
# pd.DataFrame(content).to_csv('results/xiaocao_industry_block_category_rank_all_0.csv', index=False)
